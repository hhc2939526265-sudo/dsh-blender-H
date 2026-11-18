# -*- coding: utf-8 -*-
"""
自然语言解析分发模块（Blender 端）。

- 调用 AI 适配层把中文提示词解析为指令序列
- 按顺序逐条落地执行，汇总每条指令回执
- 支持 dry_run（只返回解析结果，不真正执行）
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from ..core import protocol


def dispatch(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    prompt = payload["prompt"]
    params = payload.get("params", {})
    spec, provider_name = ctx.bridge.providers.safe_call(
        "parse_natural_language", prompt, params)
    commands: List[Dict[str, Any]] = spec.get("commands", [])

    dry_run = bool(payload.get("dry_run", False))
    receipts: List[Dict[str, Any]] = []

    if not dry_run:
        for cmd in commands:
            envelope = protocol.new_command(
                cmd_type=cmd["cmd_type"], payload=cmd.get("payload", {}))
            receipt = ctx.bridge.dispatcher.execute(envelope)
            receipts.append({
                "cmd_type": receipt["cmd_type"],
                "status": receipt["status"],
                "result": receipt["result"],
                "error": receipt["error"],
            })

    return {"prompt": prompt, "provider": provider_name,
            "command_count": len(commands), "dry_run": dry_run,
            "commands": commands, "receipts": receipts}


def register(dispatcher) -> None:
    dispatcher.register("nl.dispatch", dispatch, ["prompt"])
