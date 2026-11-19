# -*- coding: utf-8 -*-
"""
指令分发器（Blender 端）。

- 指令类型 -> 处理器函数 的注册表
- 执行前参数合法性校验（必填字段 / 类型）
- 统一异常捕获：任何处理器异常都转为 FAILED 回执，绝不向上抛到网络线程
- 处理器上下文：日志器、配置、桥接核心引用（供回传 / 备份 / 导出）
"""

from __future__ import annotations

import time
import traceback
from typing import Any, Callable, Dict, List, Optional

from . import protocol
from ..utils.errors import ParamError


class HandlerContext:
    """传递给处理器的运行上下文。"""

    def __init__(self, bridge, logger, config: Dict[str, Any]):
        self.bridge = bridge
        self.logger = logger
        self.config = config

    def log(self, level: str, msg: str) -> None:
        getattr(self.logger, level, self.logger.info)(msg)


# 处理器签名：(payload: dict, ctx: HandlerContext) -> dict
HandlerFn = Callable[[Dict[str, Any], HandlerContext], Dict[str, Any]]


class Dispatcher:
    """指令注册表与执行器。"""

    def __init__(self, bridge, logger, config: Dict[str, Any]):
        self.ctx = HandlerContext(bridge, logger, config)
        self._handlers: Dict[str, HandlerFn] = {}
        self._required: Dict[str, List[str]] = {}

    def register(self, cmd_type: str, handler: HandlerFn,
                 required: Optional[List[str]] = None) -> None:
        """注册指令处理器。"""
        self._handlers[cmd_type] = handler
        self._required[cmd_type] = required or []

    def has(self, cmd_type: str) -> bool:
        return cmd_type in self._handlers

    def available_commands(self) -> List[str]:
        return sorted(self._handlers.keys())

    # ------------------------------------------------------------- 校验
    def _validate(self, cmd_type: str, payload: Dict[str, Any]) -> Dict[str, str]:
        missing = [k for k in self._required.get(cmd_type, [])
                   if k not in payload or payload[k] is None]
        if missing:
            return {"code": "E_PARAM", "message": f"缺少必填参数: {', '.join(missing)}"}
        return {}

    # ------------------------------------------------------------- 执行
    def execute(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行一条已校验信封，返回回执信封。

        任何异常都被收敛为 FAILED 回执。
        """
        cmd_id = message.get("cmd_id", "")
        cmd_type = message.get("cmd_type", "")
        payload = message.get("payload", {})

        # 协议校验
        proto_err = protocol.validate_envelope(message)
        if proto_err:
            return protocol.make_result(cmd_id, cmd_type, protocol.STATUS_FAILED,
                                        error=proto_err)

        handler = self._handlers.get(cmd_type)
        if handler is None:
            return protocol.make_result(
                cmd_id, cmd_type, protocol.STATUS_FAILED,
                error={"code": "E_UNKNOWN_CMD",
                       "message": f"未注册的指令类型: {cmd_type}"})

        param_err = self._validate(cmd_type, payload)
        if param_err:
            return protocol.make_result(cmd_id, cmd_type, protocol.STATUS_FAILED,
                                        error=param_err)

        started = time.time()
        try:
            result = handler(payload, self.ctx) or {}
            result["_elapsed_ms"] = round((time.time() - started) * 1000, 2)
            return protocol.make_result(cmd_id, cmd_type, protocol.STATUS_SUCCESS,
                                        result=result)
        except ParamError as exc:
            err = {"code": "E_PARAM", "message": str(exc),
                   "detail": traceback.format_exc()}
            return protocol.make_result(cmd_id, cmd_type, protocol.STATUS_FAILED,
                                        error=err)
        except KeyError as exc:
            err = {"code": "E_PARAM", "message": f"参数缺失: {exc}",
                   "detail": traceback.format_exc()}
            return protocol.make_result(cmd_id, cmd_type, protocol.STATUS_FAILED,
                                        error=err)
        except Exception as exc:  # noqa: BLE001 - 顶层兜底，保证不崩溃
            err = {"code": "E_EXEC", "message": f"{type(exc).__name__}: {exc}",
                   "detail": traceback.format_exc()}
            self.ctx.log("error", f"指令执行失败 [{cmd_type}] {exc}")
            return protocol.make_result(cmd_id, cmd_type, protocol.STATUS_FAILED,
                                        error=err)
