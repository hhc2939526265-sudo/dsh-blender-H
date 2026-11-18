# -*- coding: utf-8 -*-
"""
多模态文件分片传输（Blender 端）。

入站（DSH -> Blender）：
- ``transfer.begin`` 登记会话，记录文件名 / 总大小 / MD5 / 分片数
- ``transfer.chunk`` 按分片索引落盘到内存缓冲，支持断点续传：
  重连后 begin 阶段返回缺失分片索引，客户端仅补发缺失分片
- ``transfer.end`` 合并分片、MD5 校验，校验通过后写入最终路径

出站（Blender -> DSH）：
- ``split_file`` 将本地文件切分为分片列表，供上层逐片发送

仅使用标准库（hashlib / base64 / os / json / threading）。
"""

from __future__ import annotations

import os
import json
import base64
import hashlib
import threading
from typing import Any, Dict, List, Optional


class TransferSession:
    """单个文件的分片接收会话。"""

    def __init__(self, file_id: str, filename: str, total_size: int,
                 md5: str, chunk_count: int, save_dir: str):
        self.file_id = file_id
        self.filename = filename
        self.total_size = total_size
        self.md5 = md5.lower()
        self.chunk_count = chunk_count
        self.save_dir = save_dir
        self.chunks: Dict[int, bytes] = {}
        self.received_bytes = 0
        self.created_at = __import__("time").time()

    def missing_indexes(self) -> List[int]:
        """返回尚未收到的分片索引列表。"""
        return [i for i in range(self.chunk_count) if i not in self.chunks]

    def add_chunk(self, index: int, data: bytes, max_chunk_bytes: int) -> None:
        """
        登记一个分片，做单分片大小与累计字节硬校验。

        :raises ValueError: 单分片超限，或累计字节超出登记的 total_size
        """
        if len(data) > max_chunk_bytes:
            raise ValueError(f"单分片超出大小上限 {max_chunk_bytes} 字节")
        # 断点续传重复补发同一索引时，先扣减旧分片字节，避免重复计数
        old = self.chunks.get(index)
        new_total = self.received_bytes - (len(old) if old else 0) + len(data)
        if self.total_size > 0 and new_total > self.total_size:
            raise ValueError("累计接收字节超出登记的文件总大小")
        self.chunks[index] = data
        self.received_bytes = new_total

    def is_complete(self) -> bool:
        """分片索引集合必须恰好覆盖 0..chunk_count-1，防止索引错位漏片。"""
        return len(self.chunks) == self.chunk_count and \
            set(self.chunks.keys()) == set(range(self.chunk_count))

    def merge(self) -> str:
        """合并分片并落盘，返回最终文件路径。"""
        if not self.is_complete():
            raise ValueError("分片不完整或索引错位，无法合并")
        os.makedirs(self.save_dir, exist_ok=True)
        safe_name = os.path.basename(self.filename) or f"{self.file_id}.bin"
        final_path = os.path.join(self.save_dir, safe_name)
        with open(final_path, "wb") as fh:
            for i in range(self.chunk_count):
                fh.write(self.chunks[i])
        return final_path


def md5_of_file(path: str) -> str:
    """计算文件 MD5（分块读取，避免大文件一次性入内存）。"""
    digest = hashlib.md5()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(1 << 20)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def md5_of_bytes(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


class TransferManager:
    """分片会话注册表，线程安全。"""

    def __init__(self, save_dir: str, chunk_size: int,
                 verify_md5: bool = True, resume_enabled: bool = True,
                 max_total_bytes: int = 2 * 1024 ** 3):
        self.save_dir = save_dir
        self.chunk_size = chunk_size
        self.verify_md5 = verify_md5
        self.resume_enabled = resume_enabled
        self.max_total_bytes = max_total_bytes
        self._sessions: Dict[str, TransferSession] = {}
        self._lock = threading.Lock()
        os.makedirs(save_dir, exist_ok=True)

    # ------------------------------------------------------------- 入站
    def begin(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        登记 / 恢复会话。

        :return: ack 结果，含 missing 分片索引与是否续传
        """
        file_id = payload["file_id"]
        filename = payload.get("filename", f"{file_id}.bin")
        total_size = int(payload.get("total_size", 0))
        md5 = str(payload.get("md5", "")).lower()
        chunk_count = int(payload.get("chunk_count", 0))

        # 入参合法性校验：分片数与总大小必须为正且不超过上限
        if chunk_count <= 0:
            return {"ok": False, "error": "chunk_count 必须为正整数"}
        if total_size < 0 or total_size > self.max_total_bytes:
            return {"ok": False,
                    "error": f"文件大小超出上限 {self.max_total_bytes} 字节"}

        with self._lock:
            existing = self._sessions.get(file_id)
            if existing is not None and self.resume_enabled:
                missing = existing.missing_indexes()
                return {"file_id": file_id, "resumed": True,
                        "missing": missing, "received": len(existing.chunks),
                        "chunk_count": chunk_count}

            session = TransferSession(file_id, filename, total_size, md5,
                                       chunk_count, self.save_dir)
            self._sessions[file_id] = session
            return {"file_id": file_id, "resumed": False,
                    "missing": list(range(chunk_count)),
                    "received": 0, "chunk_count": chunk_count}

    def add_chunk(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """接收一个分片。"""
        file_id = payload["file_id"]
        index = int(payload["index"])
        data = base64.b64decode(payload.get("data", ""))
        with self._lock:
            session = self._sessions.get(file_id)
            if session is None:
                return {"file_id": file_id, "ok": False,
                        "error": "会话不存在，请先 begin"}
            if not (0 <= index < session.chunk_count):
                return {"file_id": file_id, "ok": False,
                        "error": f"分片索引越界: {index}（0~{session.chunk_count - 1}）"}
            try:
                session.add_chunk(index, data, self.chunk_size)
            except ValueError as exc:
                # 大小超限：丢弃整个会话，避免脏分片占用内存
                self._sessions.pop(file_id, None)
                return {"file_id": file_id, "ok": False, "error": str(exc)}
            return {"file_id": file_id, "ok": True,
                    "received": len(session.chunks),
                    "received_bytes": session.received_bytes,
                    "chunk_count": session.chunk_count}

    def finish(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """合并分片并校验 MD5。"""
        file_id = payload["file_id"]
        with self._lock:
            session = self._sessions.get(file_id)
            if session is None:
                return {"ok": False, "error": "会话不存在"}
            if not session.is_complete():
                return {"ok": False, "error": "分片不完整",
                        "missing": session.missing_indexes()}
            final_path = session.merge()

        # MD5 校验（在锁外做 IO，避免长时间持锁）
        if self.verify_md5 and session.md5:
            actual = md5_of_file(final_path)
            if actual != session.md5:
                os.remove(final_path)
                return {"ok": False, "error": "MD5 校验失败",
                        "expected": session.md5, "actual": actual}

        with self._lock:
            self._sessions.pop(file_id, None)
        return {"ok": True, "file_id": file_id, "path": final_path,
                "filename": session.filename, "size": os.path.getsize(final_path),
                "md5": session.md5}

    # ------------------------------------------------------------- 出站
    def split_file(self, path: str) -> Dict[str, Any]:
        """
        将本地文件切分为 base64 分片列表。

        :return: {file_id, filename, total_size, md5, chunk_count, chunks:[{index,data}]}
        """
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        file_id = hashlib.md5(path.encode()).hexdigest()[:12]
        filename = os.path.basename(path)
        total_size = os.path.getsize(path)
        md5 = md5_of_file(path)
        chunks: List[Dict[str, Any]] = []
        index = 0
        with open(path, "rb") as fh:
            while True:
                block = fh.read(self.chunk_size)
                if not block:
                    break
                chunks.append({"index": index,
                               "data": base64.b64encode(block).decode("ascii")})
                index += 1
        return {"file_id": file_id, "filename": filename, "total_size": total_size,
                "md5": md5, "chunk_count": len(chunks), "chunks": chunks}

    def cleanup_idle(self, max_age_seconds: int) -> int:
        """清理超时未完成的残留会话，返回清理数量。"""
        import time
        now = time.time()
        with self._lock:
            stale = [fid for fid, s in self._sessions.items()
                     if now - s.created_at > max_age_seconds]
            for fid in stale:
                self._sessions.pop(fid, None)
        return len(stale)
