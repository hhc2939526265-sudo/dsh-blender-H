# -*- coding: utf-8 -*-
"""WebSocket 服务端回环集成测试（标准库，无需 Blender）。"""

import base64
import os
import struct
import sys
import threading
import time
import unittest
import socket

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "blender_addon"))

from core.ws_server import WSServer  # noqa: E402


def _ws_frame(opcode: int, payload: bytes, mask: bool = True, fin: int = 1) -> bytes:
    header = bytearray([(0x80 if fin else 0x00) | opcode])
    n = len(payload)
    if n < 126:
        header.append(0x80 | n)
    elif n < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack("!H", n))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack("!Q", n))
    mask_key = os.urandom(4)
    if mask:
        header.extend(mask_key)
        payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    return bytes(header) + payload


def _read_frame(sock: socket.socket):
    def exact(n):
        buf = b""
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                return None
            buf += chunk
        return buf

    header = exact(2)
    if header is None:
        return None
    b1, b2 = header
    opcode = b1 & 0x0F
    length = b2 & 0x7F
    if length == 126:
        length = struct.unpack("!H", exact(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", exact(8))[0]
    payload = exact(length) if length else b""
    return opcode, payload


class TestWSServer(unittest.TestCase):

    def setUp(self):
        self.received = []
        self.events = []
        self.server = WSServer(
            host="127.0.0.1", port=0,
            on_message=lambda cid, text: self.received.append(text),
            on_status=lambda s, d: self.events.append(s),
            heartbeat_interval=30, heartbeat_timeout=10,
        )
        # 端口 0 由系统分配；直接绑定后读取实际端口
        self.server._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server._sock.bind(("127.0.0.1", 0))
        self.server._sock.listen(8)
        self.port = self.server._sock.getsockname()[1]
        self.server._running = True
        self.server._accept_thread = threading.Thread(
            target=self.server._accept_loop, daemon=True)
        self.server._accept_thread.start()

    def tearDown(self):
        self.server.stop()

    def _handshake(self):
        sock = socket.create_connection(("127.0.0.1", self.port))
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            "GET / HTTP/1.1\r\nHost: 127.0.0.1\r\nUpgrade: websocket\r\n"
            "Connection: Upgrade\r\nSec-WebSocket-Key: " + key +
            "\r\nSec-WebSocket-Version: 13\r\n\r\n")
        sock.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += sock.recv(1024)
        self.assertIn(b"101", resp.split(b"\r\n")[0])
        return sock

    def test_text_frame_delivered(self):
        sock = self._handshake()
        time.sleep(0.2)
        sock.sendall(_ws_frame(0x1, b'{"hello": "bridge"}'))
        time.sleep(0.3)
        self.assertEqual(self.received, ['{"hello": "bridge"}'])
        sock.close()

    def test_pong_reply(self):
        sock = self._handshake()
        time.sleep(0.2)
        sock.sendall(_ws_frame(0x9, b"ping-data"))
        opcode, payload = _read_frame(sock)
        self.assertEqual(opcode, 0xA)
        self.assertEqual(payload, b"ping-data")
        sock.close()

    def test_multibyte_fragment_assembly(self):
        sock = self._handshake()
        time.sleep(0.2)
        # 模拟两帧分片：首帧 FIN=0，续帧 FIN=1
        part1 = b'{"cmd": "'
        part2 = '中文"}'.encode("utf-8")
        sock.sendall(_ws_frame(0x1, part1, mask=True, fin=0))
        sock.sendall(_ws_frame(0x0, part2, mask=True, fin=1))
        time.sleep(0.3)
        self.assertEqual(self.received, ['{"cmd": "中文"}'])
        sock.close()


if __name__ == "__main__":
    unittest.main()
