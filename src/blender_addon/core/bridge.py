# -*- coding: utf-8 -*-
"""
桥接主控（Blender 端）。

聚合通信层、传输层、分发层、AI 适配层、备份层与业务处理器，对外暴露统一生命周期：

- ``start()``：加载配置 → 构建各子系统 → 启动本地 WebSocket 服务
- ``on_main_thread_tick()``：由主线程定时器调用，排空指令队列并落地执行
- ``stop()``：停止服务、清空队列、释放缓存

协议报文流转：
    DSH --文本帧--> WSServer.on_message --解析校验--> CommandQueue
    主线程定时器 --drain--> Dispatcher.execute --> 回执信封 --send_text--> DSH
"""

from __future__ import annotations

import os
import json
import time
import traceback
from typing import Any, Dict, List, Optional

from . import protocol
from .ws_server import WSServer
from .transfer import TransferManager
from .dispatcher import Dispatcher
from .queue import CommandQueue
from ..ai.registry import ProviderRegistry
from ..utils import paths
from ..utils.backup import BackupManager
from ..handlers import (
    modeling, character, animation, effects, material,
    render, scene, export, nl, pipeline, addons,
)


class Bridge:
    """桥接主控单例。"""

    def __init__(self, config: Dict[str, Any], logger):
        self.config = config
        self.logger = logger

        # 子系统初始化
        self.transfer = TransferManager(
            save_dir=paths.subdir("transfer"),
            chunk_size=int(config.get("chunk_size", 64 * 1024)),
            verify_md5=bool(config.get("verify_md5", True)),
            resume_enabled=bool(config.get("resume_enabled", True)),
        )
        self.backup = BackupManager(
            backup_dir=paths.subdir("backup"),
            max_slots=int(config.get("max_backup_slots", 5)),
        )
        self.providers = ProviderRegistry(config, logger)
        self.dispatcher = Dispatcher(self, logger, config)
        self.queue = CommandQueue(
            mode=config.get("queue_mode", "serial"),
            max_parallel=int(config.get("max_parallel", 2)),
        )

        self.ws: Optional[WSServer] = None
        self._conn_id: Optional[str] = None
        self._started_at: float = 0.0
        self._stats = {"total": 0, "success": 0, "failed": 0}

        self._register_handlers()

    # ------------------------------------------------------------- 处理器挂载
    def _register_handlers(self) -> None:
        """按模块注册全部业务指令处理器。"""
        modeling.register(self.dispatcher)
        character.register(self.dispatcher)
        animation.register(self.dispatcher)
        effects.register(self.dispatcher)
        material.register(self.dispatcher)
        render.register(self.dispatcher)
        scene.register(self.dispatcher)
        export.register(self.dispatcher)
        nl.register(self.dispatcher)
        pipeline.register(self.dispatcher)
        addons.register(self.dispatcher)

        # 系统 / 传输类指令直接在主控层处理，不进入主线程业务队列
        self.dispatcher.register(protocol.CommandType.TRANSFER_BEGIN,
                                 self._h_transfer_begin)
        self.dispatcher.register(protocol.CommandType.TRANSFER_CHUNK,
                                 self._h_transfer_chunk)
        self.dispatcher.register(protocol.CommandType.TRANSFER_END,
                                 self._h_transfer_end)

    # ------------------------------------------------------------- 生命周期
    def start(self) -> bool:
        """启动桥接服务；返回是否成功监听。"""
        if self.ws and self.ws.is_running():
            return True
        host = self.config.get("host", "127.0.0.1")
        port = int(self.config.get("port", 8765))
        self.ws = WSServer(
            host=host, port=port,
            on_message=self._on_ws_message,
            on_status=self._on_status,
            heartbeat_interval=int(self.config.get("heartbeat_interval", 30)),
            heartbeat_timeout=int(self.config.get("heartbeat_timeout", 10)),
            logger=self.logger,
        )
        ok = self.ws.start()
        if ok:
            self._started_at = time.time()
        return ok

    def stop(self) -> None:
        """停止服务并清理运行期资源。"""
        if self.ws is not None:
            self.ws.stop()
        pending = self.queue.clear()
        if pending:
            self.logger.info(f"停止时清空排队指令 {pending} 条")
        # 释放闲置临时文件
        try:
            paths.cleanup_temp(int(self.config.get("idle_release_seconds", 300)))
        except OSError:
            pass

    def is_running(self) -> bool:
        return self.ws is not None and self.ws.is_running()

    @property
    def current_conn_id(self) -> Optional[str]:
        """最近一条指令所属连接 ID（出站回传目标）。"""
        return self._conn_id

    # ------------------------------------------------------------- 网络回调
    def _on_status(self, status: str, detail: str) -> None:
        self.logger.info(f"连接状态: {status} | {detail}")
        self._broadcast_event("system.status",
                              {"status": status, "detail": detail,
                               "connections": self.ws.connection_count()
                               if self.ws else 0})

    def _on_ws_message(self, conn_id: str, text: str) -> None:
        """WebSocket 收包入口（网络线程）。"""
        try:
            message = json.loads(text)
        except ValueError:
            self._send_raw(conn_id, protocol.make_result(
                "", "", protocol.STATUS_FAILED,
                error={"code": "E_JSON", "message": "JSON 解析失败"}))
            return

        err = protocol.validate_envelope(message)
        if err:
            self._send_raw(conn_id, protocol.make_result(
                message.get("cmd_id", ""), message.get("cmd_type", ""),
                protocol.STATUS_FAILED, error=err))
            return

        cmd_type = message["cmd_type"]

        # 心跳 / 握手类指令直接应答，不入队
        if cmd_type == protocol.CommandType.HEARTBEAT or cmd_type == protocol.CommandType.PING:
            self._send_raw(conn_id, protocol.make_result(
                message["cmd_id"], cmd_type, protocol.STATUS_SUCCESS,
                result={"pong": True, "ts": time.time()}))
            return
        if cmd_type == protocol.CommandType.SYSTEM_STOP:
            cleared = self.queue.clear()
            self._send_raw(conn_id, protocol.make_result(
                message["cmd_id"], cmd_type, protocol.STATUS_SUCCESS,
                result={"cleared": cleared}))
            return
        if cmd_type == protocol.CommandType.HANDSHAKE:
            self._conn_id = conn_id
            self._send_raw(conn_id, protocol.make_result(
                message["cmd_id"], cmd_type, protocol.STATUS_SUCCESS,
                result={"server": "blender-addon",
                        "version": self.config.get("addon_version", "1.0.0"),
                        "commands": self.dispatcher.available_commands()}))
            return

        # 其余指令进入主线程队列
        self._conn_id = conn_id
        self.queue.enqueue(conn_id, message)
        self._stats["total"] += 1

    # ------------------------------------------------------------- 主线程节拍
    def on_main_thread_tick(self) -> float:
        """
        主线程定时器回调：排空队列并执行。

        :return: 定时器下次触发间隔（秒），返回负数可停止定时器
        """
        items = self.queue.drain()
        for conn_id, message in items:
            self._execute_one(conn_id, message)
        return 0.1  # 100ms 节拍

    def _execute_one(self, conn_id: str, message: Dict[str, Any]) -> None:
        """执行单条指令并回传回执。"""
        cmd_type = message.get("cmd_type", "")
        try:
            receipt = self.dispatcher.execute(message)
        except Exception as exc:  # 兜底，绝不让定时器线程崩溃
            receipt = protocol.make_result(
                message.get("cmd_id", ""), cmd_type, protocol.STATUS_FAILED,
                error={"code": "E_FATAL", "message": str(exc),
                       "detail": traceback.format_exc()})
        status = receipt.get("status")
        if status == protocol.STATUS_SUCCESS:
            self._stats["success"] += 1
        else:
            self._stats["failed"] += 1
        self._send_raw(conn_id, receipt)

    # ------------------------------------------------------------- 传输指令
    def _h_transfer_begin(self, payload: Dict[str, Any], ctx) -> Dict[str, Any]:
        return self.transfer.begin(payload)

    def _h_transfer_chunk(self, payload: Dict[str, Any], ctx) -> Dict[str, Any]:
        return self.transfer.add_chunk(payload)

    def _h_transfer_end(self, payload: Dict[str, Any], ctx) -> Dict[str, Any]:
        return self.transfer.finish(payload)

    # ------------------------------------------------------------- 出站发送
    def _send_raw(self, conn_id: str, envelope: Dict[str, Any]) -> None:
        if self.ws is None:
            return
        text = json.dumps(envelope, ensure_ascii=False)
        if conn_id:
            self.ws.send_text(conn_id, text)
        else:
            self.ws.broadcast_text(text)

    def _broadcast_event(self, cmd_type: str, result: Dict[str, Any]) -> None:
        """向全部连接推送一条异步事件（进度 / 状态 / 预览）。"""
        if self.ws is None:
            return
        envelope = protocol.make_result("", cmd_type, protocol.STATUS_SUCCESS,
                                        result=result)
        self.ws.broadcast_text(json.dumps(envelope, ensure_ascii=False))

    def push_event(self, cmd_type: str, result: Dict[str, Any]) -> None:
        """供业务处理器主动推送进度 / 预览事件。"""
        self._broadcast_event(cmd_type, result)

    def send_file_back(self, conn_id: str, path: str,
                       meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        出站文件回传：分片切分 → 逐片发送 → 结束回执。

        :return: 传输元信息（file_id / 文件名 / 大小 / MD5 / 分片数）
        """
        packed = self.transfer.split_file(path)
        meta = meta or {}
        # begin
        self._send_raw(conn_id, protocol.make_result(
            "", protocol.CommandType.TRANSFER_BEGIN, protocol.STATUS_SUCCESS,
            result={**{k: packed[k] for k in
                       ("file_id", "filename", "total_size", "md5", "chunk_count")},
                    "meta": meta}))
        # chunks
        for chunk in packed["chunks"]:
            self._send_raw(conn_id, protocol.make_result(
                "", protocol.CommandType.TRANSFER_CHUNK, protocol.STATUS_SUCCESS,
                result={"file_id": packed["file_id"], "index": chunk["index"],
                        "data": chunk["data"]}))
        # end
        self._send_raw(conn_id, protocol.make_result(
            "", protocol.CommandType.TRANSFER_END, protocol.STATUS_SUCCESS,
            result={"file_id": packed["file_id"], "filename": packed["filename"],
                     "md5": packed["md5"], "size": packed["total_size"],
                     "meta": meta}))
        return {"file_id": packed["file_id"], "filename": packed["filename"],
                "size": packed["total_size"], "md5": packed["md5"],
                "chunk_count": packed["chunk_count"]}

    # ------------------------------------------------------------- 状态查询
    def status(self) -> Dict[str, Any]:
        """汇总桥接状态，供面板与 DSH 端查询。"""
        return {
            "running": self.is_running(),
            "host": self.config.get("host"),
            "port": self.config.get("port"),
            "connections": self.ws.connection_count() if self.ws else 0,
            "pending": self.queue.pending_count(),
            "stats": dict(self._stats),
            "provider": self.providers.active_name,
            "uptime": round(time.time() - self._started_at, 2) if self._started_at else 0.0,
            "commands": self.dispatcher.available_commands(),
        }
