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
import hmac
import socket
import struct
import threading
import time
from urllib.parse import urlparse
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
    """WebSocket 协议级异常；``code`` 为建议的关闭码（RFC 6455 §7.4.1）。"""

    def __init__(self, message: str, code: int = 1002):
        super().__init__(message)
        self.code = code


class _Connection:
    """单条客户端连接的状态封装。"""

    def __init__(self, sock: socket.socket, addr):
        self.sock = sock
        self.addr = addr
        self.send_lock = threading.Lock()
        self.last_pong = time.time()
        self.last_ping_sent = 0.0
        self.fragments: List[bytes] = []
        self.frag_opcode: Optional[int] = None
        self.handshaked = False
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
    :param handshake_timeout: 握手读取超时（秒），超时即断开，避免空闲 TCP 占位
    :param max_message_bytes: 单条消息（含全部分片）最大字节数
    :param logger: 外部日志器
    """

    def __init__(self, host: str, port: int,
                 on_message: Callable[[str, str], None],
                 on_status: Optional[Callable[[str, str], None]] = None,
                 heartbeat_interval: int = 30, heartbeat_timeout: int = 10,
                 logger=None, auth_token: str = "",
                 allowed_origins: Optional[List[str]] = None,
                 max_connections: int = 4,
                 handshake_timeout: float = 5.0,
                 max_message_bytes: int = 8 * 1024 * 1024):
        self.host = host
        self.port = port
        self._on_message = on_message
        self._on_status = on_status or (lambda s, d: None)
        self.heartbeat_interval = heartbeat_interval
        self.heartbeat_timeout = heartbeat_timeout
        self.log = logger
        # 安全策略：共享口令 / Origin 白名单 / 并发连接上限
        self._auth_token = auth_token or ""
        self._allowed_origins = {o.lower() for o in (allowed_origins or []) if o}
        self._max_connections = max(1, int(max_connections))
        self._handshake_timeout = max(0.5, float(handshake_timeout))
        self._max_message_bytes = max(1024, int(max_message_bytes))

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
            # 握手前先设读超时：只连不握手的连接会在 handshake_timeout 后被回收，
            # 避免空闲 TCP 永久占位（本地 DoS）
            try:
                client.settimeout(self._handshake_timeout)
            except OSError:
                pass
            conn = _Connection(client, addr)
            with self._conn_lock:
                too_many = len(self._conns) >= self._max_connections * 4
            if too_many:
                # 未握手连接过多（端口扫描 / 慢速连接）：直接拒掉，别让线程被刷爆
                self._reject_raw(client, 503, "连接过多，请稍后重试")
                try:
                    client.close()
                except OSError:
                    pass
                continue
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
    @staticmethod
    def _parse_headers(req: str) -> Dict[str, str]:
        """把握手请求头解析为小写键名字典。"""
        headers: Dict[str, str] = {}
        lines = req.split("\r\n")
        for line in lines[1:]:
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        return headers

    def _check_origin(self, origin: str) -> bool:
        """校验 Origin 是否为本地回环或在白名单内；无 Origin 头视为桌面客户端放行。

        白名单同时支持两种写法：
        - 主机名（``localhost`` / ``192.168.1.9``），与 Origin 的 hostname 比较；
        - 完整 Origin（``dsh-app://app``），与 Origin 的 scheme://host 比较 ——
          DSH 桌面应用（Electron）以自定义协议加载页面，hostname 只有 ``app``。
        """
        if not origin:
            return True
        try:
            parsed = urlparse(origin)
            host = (parsed.hostname or "").lower()
        except ValueError:
            return False
        if host in ("localhost", "127.0.0.1", "::1"):
            return True
        if host and host in self._allowed_origins:
            return True
        scheme = (parsed.scheme or "").lower()
        return bool(scheme) and f"{scheme}://{parsed.netloc}".lower() in self._allowed_origins

    def _check_token(self, headers: Dict[str, str]) -> bool:
        """共享口令校验：支持 Sec-WebSocket-Protocol 末段或 Authorization: Bearer。"""
        if not self._auth_token:
            return True
        token = ""
        proto = headers.get("sec-websocket-protocol", "")
        if proto:
            parts = [p.strip() for p in proto.split(",") if p.strip()]
            token = parts[-1] if parts else ""
        authz = headers.get("authorization", "")
        if authz.lower().startswith("bearer "):
            token = authz[7:].strip()
        # 常量时间比较，避免逐字符比较泄露口令
        return hmac.compare_digest(token.encode("utf-8"),
                                   self._auth_token.encode("utf-8"))

    def _do_handshake(self, conn: _Connection) -> bool:
        """完成 HTTP Upgrade 握手，返回是否成功；校验不通过回 403 并拒绝。"""
        try:
            req = self._recv_http_headers(conn.sock)
        except (OSError, WebSocketError) as exc:
            self._safe_log("warning", f"握手读取失败: {exc}")
            return False

        headers = self._parse_headers(req)

        # 并发连接上限：只统计已完成握手的连接；未握手的连接由握手超时回收，
        # 不占名额（否则慢速连接就能把正常客户端挡在门外）
        with self._conn_lock:
            active = sum(1 for c in self._conns.values() if c.handshaked)
        if active >= self._max_connections:
            self._reject(conn, 403, "连接数已达上限")
            return False

        # Origin / 口令校验（防浏览器跨站 WebSocket 劫持 CSWSH）
        if not self._check_origin(headers.get("origin", "")):
            self._safe_log("warning", "握手 Origin 被拒绝: " + headers.get("origin", ""))
            self._reject(conn, 403, "Origin 不在白名单")
            return False
        if not self._check_token(headers):
            self._safe_log("warning", "握手口令校验失败")
            self._reject(conn, 403, "握手口令校验失败")
            return False

        key = headers.get("sec-websocket-key")
        if not key:
            self._reject(conn, 400, "缺少 Sec-WebSocket-Key")
            return False

        accept = base64.b64encode(
            hashlib.sha1((key + _GUID).encode()).digest()).decode()
        # 客户端携带子协议时回显业务名（末段口令不回显）
        proto = headers.get("sec-websocket-protocol", "")
        proto_header = ""
        if proto:
            proto_header = "Sec-WebSocket-Protocol: dsh-bridge\r\n"
        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n"
            f"{proto_header}\r\n"
        )
        try:
            conn.sock.sendall(response.encode())
            conn.handshaked = True
            try:
                conn.sock.settimeout(None)  # 业务连接不再受握手超时约束
            except OSError:
                pass
            return True
        except OSError:
            return False

    def _reject(self, conn: _Connection, status: int, reason: str) -> None:
        """握手阶段拒绝连接并回送状态行。"""
        self._reject_raw(conn.sock, status, reason)

    @staticmethod
    def _reject_raw(sock: socket.socket, status: int, reason: str) -> None:
        """向尚未注册的裸连接回送错误状态行。"""
        phrases = {400: "Bad Request", 403: "Forbidden", 503: "Service Unavailable"}
        phrase = phrases.get(status, "Forbidden")
        body = reason.encode("utf-8")
        try:
            sock.sendall(
                (f"HTTP/1.1 {status} {phrase}\r\n"
                 "Content-Type: text/plain; charset=utf-8\r\n"
                 f"Content-Length: {len(body)}\r\n"
                 "Connection: close\r\n\r\n").encode() + body)
        except OSError:
            pass

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
        except WebSocketError as exc:
            self._safe_log("warning", f"连接 {cid} 协议错误，关闭: {exc}")
            self._send_close(conn, getattr(exc, "code", 1002))
        except (OSError, struct.error) as exc:
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
        if not masked:
            # RFC 6455 §5.1：客户端帧必须掩码，否则以 1002（协议错误）关闭
            raise WebSocketError("客户端帧未按 RFC 6455 掩码")
        mask_key = self._recvexact(conn.sock, 4)
        if mask_key is None:
            return None

        if opcode >= 0x8:
            # 控制帧不可分片、载荷不超过 125 字节
            if not fin or length > 125:
                raise WebSocketError("控制帧必须 FIN 且载荷不超过 125 字节")
        if length > self._max_message_bytes:
            raise WebSocketError(
                f"单帧超出大小上限 {self._max_message_bytes} 字节", 1009)

        payload = self._recvexact(conn.sock, length) if length else b""
        if payload is None:
            return None

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
        elif opcode == _OP_CONT and conn.frag_opcode is not None:
            conn.fragments.append(payload)
        else:
            return
        if sum(len(f) for f in conn.fragments) > self._max_message_bytes:
            raise WebSocketError(
                f"消息体超出大小上限 {self._max_message_bytes} 字节", 1009)
        if fin:
            self._flush_fragments(cid, conn)

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

    def _send_close(self, conn: _Connection, code: int) -> None:
        """发送关闭帧（带 RFC 6455 状态码）并标记连接失效。"""
        try:
            self._send_frame(conn, _OP_CLOSE, struct.pack("!H", code))
        except OSError:
            pass
        conn.alive = False

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
                if not conn.handshaked:
                    continue  # 握手阶段的连接由 handshake_timeout 回收
                if now - conn.last_pong > self.heartbeat_interval + self.heartbeat_timeout:
                    self._safe_log("warning", f"心跳超时，断开 {cid}")
                    self._close_conn(conn)
                    self._unregister(cid)
                    continue
                # 只在「已经该发 PING」且「距上次发 PING 超过一个间隔」时才发，
                # 否则 PONG 未回期间每秒都会重复发 PING
                if (now - conn.last_pong >= self.heartbeat_interval
                        and now - conn.last_ping_sent >= self.heartbeat_interval):
                    try:
                        self._send_frame(conn, _OP_PING, b"dsh-heartbeat")
                        conn.last_ping_sent = now
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
