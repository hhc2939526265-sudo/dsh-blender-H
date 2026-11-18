# -*- coding: utf-8 -*-
"""
场景保护模块（Blender 端）。

- 复杂操作前自动备份场景（环形槽位）
- 一键回滚到指定备份
- 工程导出 / 导入（.blend）
"""

from __future__ import annotations

import os
import bpy
from typing import Any, Dict

from ..utils import paths


def backup(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    record = ctx.bridge.backup.snapshot(label=payload.get("label", "manual"))
    return {"backup": record, "slots": ctx.bridge.backup.list_slots()}


def rollback(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    slot = payload.get("slot")
    result = ctx.bridge.backup.rollback(None if slot is None else int(slot))
    return result


def export_scene(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """把当前工程另存为副本并回传路径（不切换当前工程）。"""
    out_dir = paths.subdir("temp")
    os.makedirs(out_dir, exist_ok=True)
    filepath = os.path.join(out_dir, payload.get("filename", "scene.blend"))
    bpy.ops.wm.save_as_mainfile(filepath=filepath, copy=True)
    back = ctx.bridge.send_file_back(ctx.bridge.current_conn_id, filepath,
                                     {"kind": "scene_blend"})
    return {"path": filepath, "file_back": back}


def import_scene(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    filepath = payload["filepath"]
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"工程文件不存在: {filepath}")
    bpy.ops.wm.open_mainfile(filepath=filepath)
    return {"loaded": filepath, "objects": len(bpy.data.objects)}


def register(dispatcher) -> None:
    dispatcher.register("scene.backup", backup)
    dispatcher.register("scene.rollback", rollback)
    dispatcher.register("scene.export", export_scene)
    dispatcher.register("scene.import", import_scene, ["filepath"])
