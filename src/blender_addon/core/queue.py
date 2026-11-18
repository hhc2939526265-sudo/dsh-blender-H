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
import time
from collections import deque
from typing import Any, Deque, Dict, Optional, Tuple


class CommandQueue:
    """
    线程安全的指令等待队列。

    超时说明：``command_timeout`` 仅作为**排队等待超时**——条目在队列中等待
    超过该时长即被丢弃并计入 dropped。Blender 算子必须在主线程顺序落地，
    主线程不可抢占，正在执行的指令无法被中途中断；真正的执行超时需配合后台
    线程执行模型，当前版本不做伪实现。
    """

    def __init__(self, mode: str = "serial", max_parallel: int = 2,
                 command_timeout: float = 120.0):
        self.mode = mode
        self.max_parallel = max(1, int(max_parallel))
        self.command_timeout = float(command_timeout)
        self._buf: Deque[Tuple[str, Dict[str, Any], float]] = deque()
        self._lock = threading.Lock()
        self._dropped = 0

    def enqueue(self, conn_id: str, message: Dict[str, Any]) -> None:
        """入队一条待执行指令，记录入队时间戳。"""
        with self._lock:
            self._buf.append((conn_id, message, time.monotonic()))

    def drain(self, batch_limit: Optional[int] = None):
        """
        取出本节拍待执行条目；先剔除等待超时的陈旧条目。

        :return: 列表 ``[(conn_id, message), ...]``
        """
        limit = batch_limit or (1 if self.mode == "serial" else self.max_parallel)
        now = time.monotonic()
        with self._lock:
            # 剔除排队超时条目（队首连续超时即丢弃，避免陈旧指令长期占位）
            while self._buf and (now - self._buf[0][2]) > self.command_timeout:
                self._buf.popleft()
                self._dropped += 1
            items = []
            for _ in range(limit):
                if not self._buf:
                    break
                conn_id, message, _ts = self._buf.popleft()
                items.append((conn_id, message))
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
