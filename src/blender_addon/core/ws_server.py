# -*- coding: utf-8 -*-
"""
本地 WebSocket 服务端（Blender 端）。

实现要点（仅依赖 Python 标准库，无需 pip 安装）：
- RFC6455 握手与帧编解码（文本 / 二进制 /  Ping / Pong / Close / 分片续帧）
- 独立 accept 线程 + 每连接独立处理线程，不阻塞 Blender 主线程
- 30s 心跳：定时 Ping，超时未收到 Pong 主动断开；响应客户端 Ping
- 连接注册表 + 发送锁，支持向指定 / 全部连接广播消息
- 全链路异常捕获，单连接异常不影响服务整体

上层通过 ``on_message`` 回调拿到已解码的文本消息（JSON 字符串）。
"""

from __future__ import annotations

import os
import base64
import hashlib
import socket
import struct
import threading
import time
from typing import Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# 帧操作码
# ---------------------------------------------------------------------------
_OP_CONT = 0x0
_OP_TEXT = 0x1
_OP_BINARY = 0x2
_OP_CLOSE = 0x8
_OP_PING = 0x9
_OP_PONG = 0xA

_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class WebSocketError(Exception):
    """WebSocket 协议级异常。"""


class _Connection:
    """单条客户端连接的状态封装。"""

    def __init__(self, sock: socket.socket, addr):
        self.sock = sock
        self.addr = addr
        self.send_lock = threading.Lock()
        self.last_pong = time.time()
        self.fragments: List[bytes] = []
        self.frag_opcode: Optional[int] = None
        self.alive = True


class WSServer:
    """
    本地 WebSocket 长连接服务端。

    :param host: 监听地址
    :param port: 监听端口
    :param on_message: 消息回调 ``on_message(conn_id, text: str)``
    :param on_status: 连接状态回调 ``on_status(status: str, detail: str)``
    :param heartbeat_interval: 心跳间隔（秒）
    :param heartbeat_timeout: 心跳超时（秒）
    :param logger: 外部日志器
    """

    def __init__(self, host: str, port: int,
                 on_message: Callable[[str, str], None],
                 on_status: Optional[Callable[[str, str], None]] = None,
                 heartbeat_interval: int = 30, heartbeat_timeout: int = 10,
                 logger=None):
        self.host = host
        self.port = port
        self._on_message = on_message
        self._on_status = on_status or (lambda s, d: None)
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.log = logger

        self._sock: Optional[socket.socket] = None
        self._accept_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._running = False
        self._conns: Dict[str, _Connection] = {}
        self._conn_lock = threading.Lock()
        self._conn_seq = 0

    # ------------------------------------------------------------------ 启动
    def start(self) -> bool:
        """启动服务；端口被占用或地址非法时返回 False。"""
        if self._running:
            return True
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._sock.bind((self.host, self.port))
            self._sock.listen(8)
            self._sock.settimeout(1.0)
        except OSError as exc:
            self._safe_log("error", f"WebSocket 绑定失败 {self.host}:{self.port}: {exc}")
            return False

        self._running = True
        self._accept_thread = threading.Thread(target=self._accept_loop,
                                                name="dsh-ws-accept", daemon=True)
        self._accept_thread.start()
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop,
                                                  name="dsh-ws-heartbeat", daemon=True)
        self._heartbeat_thread.start()
        self._safe_log("info", f"WebSocket 服务已启动 ws://{self.host}:{self.port}")
        self._on_status("connected", f"服务监听 {self.host}:{self.port}")
        return True

    def stop(self) -> None:
        """停止服务并关闭全部连接。"""
        self._running = False
        with self._conn_lock:
            for conn in list(self._conns.values()):
                self._close_conn(conn)
            self._conns.clear()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._safe_log("info", "WebSocket 服务已停止")
        self._on_status("disconnected", "服务已停止")

    # ------------------------------------------------------------- 连接管理
    def _accept_loop(self) -> None:
        while self._running:
            try:
                client, addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            conn = _Connection(client, addr)
            cid = self._register(conn)
            t = threading.Thread(target=self._handle_client, args=(cid, conn),
                                 name=f"dsh-ws-{cid}", daemon=True)
            t.start()

    def _register(self, conn: _Connection) -> str:
        with self._conn_lock:
            self._conn_seq += 1
            cid = f"conn-{self._conn_seq}"
            self._conns[cid] = conn
        return cid

    def _unregister(self, cid: str) -> None:
        with self._conn_lock:
            self._conns.pop(cid, None)

    # ------------------------------------------------------------- 握手
    def _do_handshake(self, conn: _Connection) -> bool:
        """完成 HTTP Upgrade 握手，返回是否成功。"""
        try:
            req = self._recv_http_headers(conn.sock)
        except (OSError, WebSocketError) as exc:
            self._safe_log("warning", f"握手读取失败: {exc}")
            return False

        key = None
        for line in req.split("\r\n"):
            if line.lower().startswith("sec-websocket-key:"):
                key = line.split(":", 1)[1].strip()
                break
        if not key:
            return False

        accept = base64.b64encode(
            hashlib.sha1((key + _GUID).encode()).digest()).decode()
        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n\r\n"
        )
        try:
            conn.sock.sendall(response.encode())
            return True
        except OSError:
            return False

    @staticmethod
    def _recv_http_headers(sock: socket.socket) -> str:
        """逐行读取握手请求头，遇到空行结束。"""
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = sock.recv(1024)
            if not chunk:
                raise WebSocketError("握手连接被关闭")
            data += chunk
            if len(data) > 65536:
                raise WebSocketError("握手请求头超长")
        return data.decode("latin-1")

    # ------------------------------------------------------------- 帧读写
    def _handle_client(self, cid: str, conn: _Connection) -> None:
        if not self._do_handshake(conn):
            self._close_conn(conn)
            self._unregister(cid)
            return
        self._safe_log("info", f"客户端接入: {conn.addr}")
        self._on_status("connected", f"客户端 {conn.addr} 已接入")

        try:
            while self._running and conn.alive:
                frame = self._read_frame(conn)
                if frame is None:
                    break
                fin, opcode, payload = frame
                self._dispatch_frame(cid, conn, fin, opcode, payload)
        except (OSError, WebSocketError, struct.error) as exc:
            self._safe_log("warning", f"连接 {cid} 异常: {exc}")
        finally:
            self._close_conn(conn)
            self._unregister(cid)
            self._safe_log("info", f"客户端断开: {cid}")
            self._on_status("disconnected", f"客户端 {conn.addr} 已断开")

    def _read_frame(self, conn: _Connection):
        """读取一帧；返回 (fin, opcode, payload)，连接关闭返回 None。"""
        header = self._recvexact(conn.sock, 2)
        if header is None:
            return None
        b1, b2 = header[0], header[1]
        fin = 1 if (b1 & 0x80) else 0
        opcode = b1 & 0x0F
        masked = b2 & 0x80
        length = b2 & 0x7F

        if length == 126:
            ext = self._recvexact(conn.sock, 2)
            if ext is None:
                return None
            length = struct.unpack("!H", ext)[0]
        elif length == 127:
            ext = self._recvexact(conn.sock, 8)
            if ext is None:
                return None
            length = struct.unpack("!Q", ext)[0]

        mask_key = b""
        if masked:
            mask_key = self._recvexact(conn.sock, 4)
            if mask_key is None:
                return None

        payload = self._recvexact(conn.sock, length) if length else b""
        if payload is None:
            return None

        if masked:
            payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
        return fin, opcode, payload

    @staticmethod
    def _recvexact(sock: socket.socket, n: int) -> Optional[bytes]:
        """精确读取 n 字节；连接关闭返回 None。"""
        if n == 0:
            return b""
        buf = bytearray()
        while len(buf) < n:
            try:
                chunk = sock.recv(n - len(buf))
            except OSError:
                return None
            if not chunk:
                return None
            buf.extend(chunk)
        return bytes(buf)

    def _dispatch_frame(self, cid: str, conn: _Connection,
                        fin: int, opcode: int, payload: bytes) -> None:
        """按操作码分发帧：控制帧直接响应，数据帧按 FIN 标志组装后续帧回调。"""
        if opcode == _OP_PING:
            self._send_frame(conn, _OP_PONG, payload)
            return
        if opcode == _OP_PONG:
            conn.last_pong = time.time()
            return
        if opcode == _OP_CLOSE:
            self._send_frame(conn, _OP_CLOSE, b"")
            conn.alive = False
            return
        if opcode == _OP_BINARY:
            self._safe_log("debug", f"收到二进制帧 {len(payload)} 字节")
            return

        # 文本 / 分片续帧组装（依据 FIN 标志判断是否为最后一片）
        if opcode == _OP_TEXT:
            conn.fragments = [payload]
            conn.frag_opcode = _OP_TEXT
            if fin:
                self._flush_fragments(cid, conn)
        elif opcode == _OP_CONT and conn.frag_opcode is not None:
            conn.fragments.append(payload)
            if fin:
                self._flush_fragments(cid, conn)
        else:
            return

    def _flush_fragments(self, cid: str, conn: _Connection) -> None:
        """组装分片并回调上层。"""
        full = b"".join(conn.fragments)
        conn.fragments = []
        conn.frag_opcode = None
        if not full:
            return
        try:
            text = full.decode("utf-8")
        except UnicodeDecodeError:
            self._safe_log("warning", "收到非法 UTF-8 文本帧，已丢弃")
            return
        try:
            self._on_message(cid, text)
        except Exception as exc:  # 回调内部异常不得拖垮连接线程
            self._safe_log("error", f"消息回调异常: {exc}")

    # ------------------------------------------------------------- 帧发送
    def _send_frame(self, conn: _Connection, opcode: int, payload: bytes) -> None:
        """发送一帧（服务端不掩码）。"""
        header = bytearray()
        header.append(0x80 | opcode)
        n = len(payload)
        if n < 126:
            header.append(n)
        elif n < 65536:
            header.append(126)
            header.extend(struct.pack("!H", n))
        else:
            header.append(127)
            header.extend(struct.pack("!Q", n))
        with conn.send_lock:
            conn.sock.sendall(bytes(header) + payload)

    def send_text(self, cid: str, text: str) -> bool:
        """向指定连接发送文本消息。"""
        with self._conn_lock:
            conn = self._conns.get(cid)
        if conn is None or not conn.alive:
            return False
        try:
            self._send_frame(conn, _OP_TEXT, text.encode("utf-8"))
            return True
        except OSError:
            conn.alive = False
            return False

    def broadcast_text(self, text: str) -> int:
        """向全部连接广播文本，返回成功发送数量。"""
        sent = 0
        with self._conn_lock:
            conns = list(self._conns.items())
        for cid, conn in conns:
            if self.send_text(cid, text):
                sent += 1
        return sent

    # ------------------------------------------------------------- 心跳
    def _heartbeat_loop(self) -> None:
        while self._running:
            time.sleep(1)
            now = time.time()
            with self._conn_lock:
                conns = list(self._conns.items())
            for cid, conn in conns:
                if now - conn.last_pong > self.heartbeat_interval + self.heartbeat_timeout:
                    self._safe_log("warning", f"心跳超时，断开 {cid}")
                    self._close_conn(conn)
                    self._unregister(cid)
                    continue
                if now - conn.last_pong >= self.heartbeat_interval:
                    try:
                        self._send_frame(conn, _OP_PING, b"dsh-heartbeat")
                    except OSError:
                        self._close_conn(conn)
                        self._unregister(cid)

    @staticmethod
    def _close_conn(conn: _Connection) -> None:
        conn.alive = False
        try:
            conn.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            conn.sock.close()
        except OSError:
            pass

    # ------------------------------------------------------------- 状态
    def connection_count(self) -> int:
        with self._conn_lock:
            return len(self._conns)

    def is_running(self) -> bool:
        return self._running

    def _safe_log(self, level: str, msg: str) -> None:
        if self.log is None:
            return
        getattr(self.log, level, self.log.info)(msg)
