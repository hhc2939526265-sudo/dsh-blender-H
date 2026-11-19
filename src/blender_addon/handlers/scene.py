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
from ..utils.errors import as_int, get_str, require_str


def backup(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    record = ctx.bridge.backup.snapshot(
        label=get_str(payload, "label", "manual"))
    return {"backup": record, "slots": ctx.bridge.backup.list_slots()}


def rollback(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    slot = payload.get("slot")
    result = ctx.bridge.backup.rollback(
        None if slot is None else as_int(slot, "slot"))
    return result


def export_scene(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """把当前工程另存为副本并回传路径（不切换当前工程）。"""
    filename = paths.safe_name(get_str(payload, "filename", "scene.blend"))
    filepath = paths.safe_join("temp", filename)
    bpy.ops.wm.save_as_mainfile(filepath=filepath, copy=True)
    back = ctx.bridge.send_file_back(ctx.bridge.current_conn_id, filepath,
                                     {"kind": "scene_blend"})
    return {"path": filepath, "file_back": back}


def import_scene(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    filepath = require_str(payload["filepath"], "filepath")
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"工程文件不存在: {filepath}")
    # 默认仅允许打开传输缓存 / 临时目录内的工程；外部路径需显式开启 allow_external_import
    if not bool(ctx.config.get("allow_external_import", False)):
        allowed = (paths.subdir("transfer"), paths.subdir("temp"))
        target = os.path.abspath(filepath)
        if not any(paths.is_within(base, target) for base in allowed):
            raise PermissionError(
                "导入工程越出传输 / 临时目录；如需打开外部路径，请在配置中开启 allow_external_import")
    bpy.ops.wm.open_mainfile(filepath=filepath)
    return {"loaded": filepath, "objects": len(bpy.data.objects)}


def register(dispatcher) -> None:
    dispatcher.register("scene.backup", backup)
    dispatcher.register("scene.rollback", rollback)
    dispatcher.register("scene.export", export_scene)
    dispatcher.register("scene.import", import_scene, ["filepath"])
