# -*- coding: utf-8 -*-
"""
端到端流水线编排（Blender 端）。

把多步业务收敛为 DSH 端可一键调用的高层指令：
- ``pipeline.character``：图片上传 → 角色建模 + 绑定（内部复用 character 处理器）
- ``pipeline.video``：视频上传 → AI 解析动作 / 特效 → 对齐到当前角色并落特效
- ``pipeline.iterate``：当前资产导出回传，供 DSH 端多轮迭代优化
"""

from __future__ import annotations

import os
import bpy
from typing import Any, Dict, List, Optional

from ..utils import paths
from . import character as Char
from . import animation as Anim
from . import effects as Eff
from . import export as Export


def _latest_armature() -> Optional[bpy.types.Object]:
    """查找场景中最近创建的骨架对象。"""
    armatures = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    return armatures[-1] if armatures else None


def _latest_mesh() -> Optional[bpy.types.Object]:
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    return meshes[-1] if meshes else None


def character_pipeline(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """图片 → 完整角色（建模 / 形状键 / 材质 / 绑定）。"""
    return Char.build(payload, ctx)


def video_pipeline(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """视频 → 动作复刻 + 特效还原，对齐当前角色。"""
    video_path: str = payload["video_path"]
    if not paths.is_within(paths.subdir("transfer"), os.path.abspath(video_path)):
        raise PermissionError("视频路径越出传输目录，拒绝解析")
    kind: str = payload.get("kind", "both")  # mocap / effect / both
    params = {
        "fps": ctx.config.get("animation_fps", 24),
        "confidence": payload.get("confidence", ctx.config.get("mocap_confidence", 0.6)),
        "effect_strength": payload.get("effect_strength",
                                       ctx.config.get("effect_strength", 0.8)),
    }

    motion_result: Dict[str, Any] = {}
    effect_result: Dict[str, Any] = {}

    # 动作捕捉
    if kind in ("mocap", "both"):
        motion, provider = ctx.bridge.providers.safe_call(
            "analyze_motion", video_path, params)
        armature = _latest_armature()
        if armature is not None:
            motion_result = Anim.mocap_apply(
                {"object": armature.name, "motion": motion}, ctx)
        else:
            motion_result = {"skipped": True, "reason": "场景中暂无骨架，请先完成角色建模"}
        motion_result["provider"] = provider

    # 特效还原
    if kind in ("effect", "both"):
        spec, provider = ctx.bridge.providers.safe_call(
            "analyze_effect", video_path, params)
        target = _latest_mesh()
        target_name = target.name if target else ""
        if target is not None:
            if spec.get("particles"):
                effect_result["particle"] = Eff.particle(
                    {"object": target_name, "particle": spec["particles"][0]}, ctx)
            if spec.get("glow"):
                effect_result["glow"] = Eff.glow(
                    {"object": target_name, "glow": spec["glow"][0]}, ctx)
            if spec.get("fluid"):
                effect_result["fluid"] = Eff.fluid(
                    {"object": target_name, "fluid": spec["fluid"][0]}, ctx)
            if spec.get("deform"):
                effect_result["deform"] = Eff.deform(
                    {"object": target_name, "deform": spec["deform"][0]}, ctx)
        if spec.get("camera"):
            effect_result["camera"] = Eff.camera_match(
                {"camera": spec["camera"]}, ctx)
        effect_result["provider"] = provider

    return {"video": video_path, "kind": kind,
            "motion": motion_result, "effect": effect_result}


def iterate_pipeline(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """当前资产导出回传，进入下一轮 AI 优化迭代。"""
    objects = payload.get("objects")
    asset = Export.export_asset({"objects": objects}, ctx)
    animation: Dict[str, Any] = {}
    armature = _latest_armature()
    if armature is not None:
        animation = Export.export_animation({"object": armature.name}, ctx)
    return {"asset": asset, "animation": animation,
            "iteration": int(payload.get("iteration", 1))}


def register(dispatcher) -> None:
    dispatcher.register("pipeline.character", character_pipeline)
    dispatcher.register("pipeline.video", video_pipeline, ["video_path"])
    dispatcher.register("pipeline.iterate", iterate_pipeline)
