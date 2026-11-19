# -*- coding: utf-8 -*-
"""
材质渲染模块（Blender 端）。

- 渲染引擎一键切换（Eevee / Cycles），按版本兼容层映射标识
- 分辨率 / 采样数 / 帧范围 / 输出路径配置
- 执行渲染（静帧 / 动画），完成后自动把成品图 / 视频分片回传 DSH 预览
"""

from __future__ import annotations

import os
import time
import bpy
from typing import Any, Dict

from ..compat import version_compat
from ..utils import paths
from ..utils.errors import (as_float, as_int, get_bool, get_int, get_str,
                            require_list)
from . import _helpers as H


def _safe_output_dir(payload: Dict[str, Any], ctx=None) -> str:
    """把渲染输出目录收敛到渲染目录下，拒绝逃逸到其他磁盘目录。"""
    base = (ctx.config.get("render_output_dir") if ctx else None) or paths.subdir("render")
    raw = get_str(payload, "output_path")
    if not raw:
        return base
    path = os.path.abspath(raw) if os.path.isabs(raw) else os.path.join(base, raw)
    return paths.require_within(base, path, "渲染输出目录")


def switch_engine(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    engine = version_compat.engine_id(get_str(payload, "engine", "EEVEE"))
    bpy.context.scene.render.engine = engine
    return {"engine": engine, "version": version_compat.version_text()}


def settings(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    scene = bpy.context.scene
    if "resolution" in payload:
        resolution = require_list(payload["resolution"], "resolution", min_len=2)
        scene.render.resolution_x = as_int(resolution[0], "resolution[0]")
        scene.render.resolution_y = as_int(resolution[1], "resolution[1]")
    if "resolution_percentage" in payload:
        scene.render.resolution_percentage = as_int(
            payload["resolution_percentage"], "resolution_percentage")
    samples = get_int(payload, "samples", 0)
    if samples:
        if scene.render.engine == "CYCLES":
            scene.cycles.samples = samples
        else:
            # Eevee Next (4.2+/5.x) 可能移除 TAA 采样属性，存在则写入，缺失则静默降级
            if hasattr(scene.eevee, "taa_render_samples"):
                scene.eevee.taa_render_samples = samples
    if "frame_start" in payload:
        scene.frame_start = as_int(payload["frame_start"], "frame_start")
    if "frame_end" in payload:
        scene.frame_end = as_int(payload["frame_end"], "frame_end")
    if "output_path" in payload:
        scene.render.filepath = _safe_output_dir(payload, ctx)
    current_samples = scene.cycles.samples if scene.render.engine == "CYCLES" \
        else getattr(scene.eevee, "taa_render_samples", samples)
    return {"engine": scene.render.engine,
            "resolution": [scene.render.resolution_x, scene.render.resolution_y],
            "samples": current_samples}


def execute(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    scene = bpy.context.scene
    # 输出路径准备（收敛到渲染目录下，防任意目录写入）
    out_dir = _safe_output_dir(payload, ctx)
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    is_animation = get_bool(payload, "animation", False)

    if is_animation:
        scene.render.filepath = os.path.join(out_dir, f"render_{stamp}_")
        scene.render.image_settings.file_format = "FFMPEG"
        bpy.ops.render.render(animation=True)
        result_path = scene.render.filepath
    else:
        ext = "png"
        scene.render.image_settings.file_format = "PNG"
        result_path = os.path.join(out_dir, f"render_{stamp}.{ext}")
        scene.render.filepath = result_path
        bpy.ops.render.render(write_still=True)

    # 渲染完成事件推送 + 文件分片回传
    ctx.bridge.push_event("render.progress", {"stage": "done", "path": result_path})
    back: Dict[str, Any] = {"transferred": False}
    if os.path.isfile(result_path):
        back = ctx.bridge.send_file_back(ctx.bridge.current_conn_id, result_path,
                                         {"kind": "render_result",
                                          "animation": is_animation})
    return {"render_path": result_path, "animation": is_animation,
            "file_back": back}


def register(dispatcher) -> None:
    dispatcher.register("render.switch_engine", switch_engine)
    dispatcher.register("render.settings", settings)
    dispatcher.register("render.execute", execute)
