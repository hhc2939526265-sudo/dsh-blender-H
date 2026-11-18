# -*- coding: utf-8 -*-
"""
特效解析映射模块（Blender 端）。

将 AI 识别出的视觉元素映射为 Blender 可编辑节点 / 系统：
- 粒子效果 → 粒子系统（数量 / 速度 / 生命周期 / 颜色渐变）
- 光效辉光 → 发光材质 + 合成辉光节点
- 流体特效 → 流体修改器参数记录（解算由物理模块触发）
- 形变动画 → 形状键 / 晶格修改器关键帧
- 镜头匹配 → 摄像机动画（推拉摇移 / 环绕）
"""

from __future__ import annotations

import bpy
import math
from typing import Any, Dict, List, Optional

from ..compat import version_compat
from . import _helpers as H


# ---------------------------------------------------------------------------
# 1. 粒子效果
# ---------------------------------------------------------------------------
def particle(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    emitter = H.require_object(payload["object"])
    spec = payload.get("particle", {})
    count = int(spec.get("count", 200))
    life = float(spec.get("life", 2.0))
    speed = float(spec.get("speed", 1.0))
    size = float(spec.get("size", 0.05))

    mod = emitter.modifiers.new(name="effect_particles", type="PARTICLE_SYSTEM")
    psys = mod.particle_system
    settings = psys.settings
    settings.count = count
    settings.lifetime = int(life * ctx.config.get("animation_fps", 24))
    settings.normal_factor = speed
    settings.particle_size = size
    settings.render_type = "HALO"

    # 颜色渐变：起始 / 结束颜色写入材质顶点色占位（渐变由色带节点在材质端衔接）
    color_start = spec.get("color_start", [1.0, 0.6, 0.2, 1.0])
    color_end = spec.get("color_end", [0.2, 0.4, 1.0, 1.0])
    ctx.bridge.push_event("effect.particle_color",
                          {"emitter": emitter.name,
                           "color_start": color_start, "color_end": color_end})
    return {"emitter": emitter.name, "count": count, "life": life,
            "speed": speed, "size": size}


# ---------------------------------------------------------------------------
# 2. 光效辉光
# ---------------------------------------------------------------------------
def glow(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    target = H.require_object(payload["object"])
    spec = payload.get("glow", {})
    intensity = float(spec.get("intensity", 1.5))
    color = spec.get("color", [1.0, 0.7, 0.3, 1.0])

    # 2.1 发光材质
    mat = bpy.data.materials.new(name=f"Glow_{target.name}")
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    version_compat.set_principled_input(bsdf, "base_color", color)
    version_compat.set_principled_input(bsdf, "emission", color)
    version_compat.set_principled_input(bsdf, "emission_strength", intensity)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    target.data.materials.append(mat)

    # 2.2 合成辉光节点（Glare），版本不可用时静默降级
    scene = bpy.context.scene
    try:
        scene.use_nodes = True
        comp = scene.node_tree
        glare = comp.nodes.new("CompositorNodeGlare")
        glare.glare_type = "FOG_GLOW"
        glare.threshold = 0.8
        comp.links.new(comp.nodes.get("Render Layers").outputs["Image"],
                       glare.inputs["Image"])
        comp.links.new(glare.outputs["Image"],
                       comp.nodes.get("Composite").inputs["Image"])
        glare_ok = True
    except (RuntimeError, TypeError, AttributeError):
        glare_ok = False

    return {"object": target.name, "intensity": intensity, "color": color,
            "compositor_glare": glare_ok}


# ---------------------------------------------------------------------------
# 3. 流体特效
# ---------------------------------------------------------------------------
def fluid(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    target = H.require_object(payload["object"])
    spec = payload.get("fluid", {})
    mod = target.modifiers.new(name="effect_fluid", type="FLUID")
    mod.settings.type = "FLOW"
    mod.settings.flow_behavior = "SMOKE"
    mod.settings.flow_velocity = float(spec.get("velocity", 0.6))
    mod.settings.use_collision = bool(spec.get("collision", True))
    return {"object": target.name, "shape": spec.get("shape", "smoke"),
            "velocity": mod.settings.flow_velocity,
            "collision": mod.settings.use_collision}


# ---------------------------------------------------------------------------
# 4. 形变动画
# ---------------------------------------------------------------------------
def deform(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    target = H.require_object(payload["object"])
    spec = payload.get("deform", {})
    amplitude = float(spec.get("amplitude", 0.2))
    timing = spec.get("timing", [0, 24])

    # 晶格变形器 + 关键帧幅度
    lattice = bpy.data.lattices.new(name=f"{target.name}_Lattice")
    lattice_obj = bpy.data.objects.new(lattice.name, lattice)
    bpy.context.collection.objects.link(lattice_obj)
    lattice_obj.parent = target

    mod = target.modifiers.new(name="effect_deform", type="LATTICE")
    mod.object = lattice_obj
    # 形变幅度关键帧（0 → amplitude → 0）
    for frame, scale_k in ((timing[0], 1.0),
                           (timing[0] + (timing[1] - timing[0]) / 2, 1.0 + amplitude),
                           (timing[1], 1.0)):
        lattice_obj.scale = (scale_k, scale_k, scale_k)
        lattice_obj.keyframe_insert(data_path="scale", frame=frame)
    return {"object": target.name, "amplitude": amplitude, "timing": timing}


# ---------------------------------------------------------------------------
# 5. 镜头匹配
# ---------------------------------------------------------------------------
def camera_match(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    spec = payload.get("camera", {})
    trajectory = spec.get("trajectory", "push")  # push / pull / pan / orbit
    distance = float(spec.get("distance", 3.0))
    fov = float(spec.get("fov", 50.0))

    cam_data = bpy.data.cameras.new(name="Match_Camera")
    cam = bpy.data.objects.new("Match_Camera", cam_data)
    bpy.context.collection.objects.link(cam)
    cam_data.lens = fov
    bpy.context.scene.camera = cam

    end_frame = int(payload.get("end_frame", 24))
    if trajectory == "push":
        cam.location = (0, distance + 2.0, 1.6)
        cam.keyframe_insert(data_path="location", frame=0)
        cam.location = (0, distance, 1.6)
        cam.keyframe_insert(data_path="location", frame=end_frame)
    elif trajectory == "pull":
        cam.location = (0, distance, 1.6)
        cam.keyframe_insert(data_path="location", frame=0)
        cam.location = (0, distance + 2.0, 1.6)
        cam.keyframe_insert(data_path="location", frame=end_frame)
    elif trajectory == "pan":
        for frame, angle in ((0, -0.4), (end_frame, 0.4)):
            cam.location = (distance * math.sin(angle), distance * math.cos(angle), 1.6)
            cam.rotation_euler = (math.radians(90), 0, angle)
            cam.keyframe_insert(data_path="location", frame=frame)
            cam.keyframe_insert(data_path="rotation_euler", frame=frame)
    else:  # orbit 环绕
        for frame in (0, end_frame):
            angle = 2 * math.pi * frame / end_frame
            cam.location = (distance * math.sin(angle), distance * math.cos(angle), 1.6)
            cam.rotation_euler = (math.radians(90), 0, angle)
            cam.keyframe_insert(data_path="location", frame=frame)
            cam.keyframe_insert(data_path="rotation_euler", frame=frame)
    return {"camera": cam.name, "trajectory": trajectory,
            "distance": distance, "end_frame": end_frame}


def register(dispatcher) -> None:
    dispatcher.register("effect.particle", particle, ["object"])
    dispatcher.register("effect.glow", glow, ["object"])
    dispatcher.register("effect.fluid", fluid, ["object"])
    dispatcher.register("effect.deform", deform, ["object"])
    dispatcher.register("effect.camera_match", camera_match)
