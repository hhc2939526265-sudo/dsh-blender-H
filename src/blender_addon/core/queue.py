# -*- coding: utf-8 -*-
"""
主线程指令队列（Blender 端）。

背景：WebSocket 收包线程不能直接执行 ``bpy.ops``（Blender 要求算子在主线程 /
正确上下文执行）。因此网络线程只负责把信封放入队列，由主线程定时器
（``bpy.app.timers``）逐批取出执行，实现「后台通信不阻塞界面、指令在主线程落地」。

队列模式：
- ``serial``：每个定时器节拍最多执行 1 条，严格 FIFO 串行
- ``parallel``：每个节拍最多执行 ``max_parallel`` 条；由于 Blender 算子仍在
  主线程顺序落地，这里的并行指批次内批量取出，不开启真正的跨线程算子执行
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any, Deque, Dict, Optional, Tuple


class CommandQueue:
    """线程安全的指令等待队列。"""

    def __init__(self, mode: str = "serial", max_parallel: int = 2):
        self.mode = mode
        self.max_parallel = max(1, int(max_parallel))
        self._buf: Deque[Tuple[str, Dict[str, Any]]] = deque()
        self._lock = threading.Lock()
        self._dropped = 0

    def enqueue(self, conn_id: str, message: Dict[str, Any]) -> None:
        """入队一条待执行指令。"""
        with self._lock:
            self._buf.append((conn_id, message))

    def drain(self, batch_limit: Optional[int] = None):
        """
        取出本节拍待执行条目。

        :return: 列表 ``[(conn_id, message), ...]``
        """
        limit = batch_limit or (1 if self.mode == "serial" else self.max_parallel)
        with self._lock:
            items = []
            for _ in range(limit):
                if not self._buf:
                    break
                items.append(self._buf.popleft())
        return items

    def pending_count(self) -> int:
        with self._lock:
            return len(self._buf)

    def clear(self) -> int:
        """清空队列，返回清除数量（停止服务 / 紧急停止时使用）。"""
        with self._lock:
            n = len(self._buf)
            self._buf.clear()
        return n

    def drop_one(self) -> None:
        with self._lock:
            self._dropped += 1

    def dropped_count(self) -> int:
        return self._dropped
