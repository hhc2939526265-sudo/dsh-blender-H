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
from . import _helpers as H


def switch_engine(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    engine = version_compat.engine_id(payload.get("engine", "EEVEE"))
    bpy.context.scene.render.engine = engine
    return {"engine": engine, "version": version_compat.version_text()}


def settings(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    scene = bpy.context.scene
    if "resolution" in payload:
        scene.render.resolution_x = int(payload["resolution"][0])
        scene.render.resolution_y = int(payload["resolution"][1])
    if "resolution_percentage" in payload:
        scene.render.resolution_percentage = int(payload["resolution_percentage"])
    samples = int(payload.get("samples", 0))
    if samples:
        if scene.render.engine == "CYCLES":
            scene.cycles.samples = samples
        else:
            # Eevee Next (4.2+/5.x) 可能移除 TAA 采样属性，存在则写入，缺失则静默降级
            if hasattr(scene.eevee, "taa_render_samples"):
                scene.eevee.taa_render_samples = samples
    if "frame_start" in payload:
        scene.frame_start = int(payload["frame_start"])
    if "frame_end" in payload:
        scene.frame_end = int(payload["frame_end"])
    if "output_path" in payload:
        scene.render.filepath = payload["output_path"]
    current_samples = scene.cycles.samples if scene.render.engine == "CYCLES" \
        else getattr(scene.eevee, "taa_render_samples", samples)
    return {"engine": scene.render.engine,
            "resolution": [scene.render.resolution_x, scene.render.resolution_y],
            "samples": current_samples}


def execute(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    scene = bpy.context.scene
    # 输出路径准备
    out_dir = payload.get("output_path") or paths.subdir("render")
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    is_animation = bool(payload.get("animation", False))

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
