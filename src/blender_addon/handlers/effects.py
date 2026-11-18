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
    if not isinstance(timing, (list, tuple)) or len(timing) < 2:
        raise ValueError("形变时序 timing 至少需要起始 / 结束两个帧号")
    start_frame, end_frame = float(timing[0]), float(timing[1])
    if end_frame <= start_frame:
        raise ValueError("形变时序结束帧必须大于起始帧")

    # 晶格变形器 + 关键帧幅度
    lattice = bpy.data.lattices.new(name=f"{target.name}_Lattice")
    lattice_obj = bpy.data.objects.new(lattice.name, lattice)
    bpy.context.collection.objects.link(lattice_obj)
    lattice_obj.parent = target

    mod = target.modifiers.new(name="effect_deform", type="LATTICE")
    mod.object = lattice_obj
    # 形变幅度关键帧（0 → amplitude → 0）
    for frame, scale_k in ((start_frame, 1.0),
                           (start_frame + (end_frame - start_frame) / 2, 1.0 + amplitude),
                           (end_frame, 1.0)):
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


# ---------------------------------------------------------------------------
# 6. 力场（风 / 推力 / 涡旋 / 湍流等场景氛围与角色受力）
# ---------------------------------------------------------------------------
_FIELD_TYPES = {
    "WIND", "FLOW", "VID", "VORTEX", "MAGNET", "FORCE", "TEXTURE",
    "TURBULENCE", "DRAG", "HARMONIC", "SMOKE_FLOW", "BOID",
}


def force_field(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    emitter = H.require_object(payload["object"])
    kind = payload.get("kind", "FLOW")
    if kind not in _FIELD_TYPES:
        raise ValueError(f"不支持的力场类型: {kind}")
    spec = payload.get("field", {})
    field = bpy.data.fields.new(name=f"{emitter.name}_Field", type=kind)
    field.strength = float(spec.get("strength", 1.0))
    if hasattr(field, "flow"):
        field.flow = float(spec.get("flow", 1.0))
    field_obj = bpy.data.objects.new(field.name, field)
    bpy.context.collection.objects.link(field_obj)
    H.set_transform(field_obj, payload)
    return {"emitter": emitter.name, "field": field.name, "kind": kind,
            "strength": field.strength}


# ---------------------------------------------------------------------------
# 7. 灯光对象（角色 / 场景布光）
# ---------------------------------------------------------------------------
_LIGHT_TYPES = {"POINT", "SUN", "SPOT", "AREA"}


def light(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    ltype = payload.get("type", "POINT")
    if ltype not in _LIGHT_TYPES:
        raise ValueError(f"不支持的灯光类型: {ltype}（POINT / SUN / SPOT / AREA）")
    data = bpy.data.lights.new(name=payload.get("name", f"Light_{ltype}"), type=ltype)
    data.energy = float(payload.get("energy", 100.0))
    color = payload.get("color", [1.0, 1.0, 1.0, 1.0])
    if len(color) >= 3:
        data.color = tuple(color[:3])
    if ltype == "SPOT":
        data.spot_size = float(payload.get("spot_size", math.radians(45.0)))
    obj = bpy.data.objects.new(data.name, data)
    bpy.context.collection.objects.link(obj)
    H.set_transform(obj, payload)
    return {"light": obj.name, "type": ltype, "energy": data.energy}


# ---------------------------------------------------------------------------
# 8. 世界环境背景（场景氛围底色 / 环境光）
# ---------------------------------------------------------------------------
def world(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    scene = bpy.context.scene
    world = scene.world or bpy.data.worlds.new("World")
    scene.world = world
    color = payload.get("color", [0.05, 0.05, 0.05, 1.0])
    strength = float(payload.get("strength", 1.0))
    applied_node = False
    try:
        world.use_nodes = True
        bg = next((n for n in world.node_tree.nodes if n.type == "BACKGROUND"), None)
        if bg is not None:
            bg.inputs["Color"].default_value = color
            bg.inputs["Strength"].default_value = strength
            applied_node = True
    except (RuntimeError, TypeError, AttributeError):
        applied_node = False
    if not applied_node:
        world.color = tuple(color[:3])
    return {"world": world.name, "color": color, "strength": strength,
            "node_setup": applied_node}


# ---------------------------------------------------------------------------
# 9. 毛发粒子（角色头发 / 绒毛）
# ---------------------------------------------------------------------------
def hair(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    target = H.require_object(payload["object"])
    spec = payload.get("hair", {})
    count = int(spec.get("count", 500))
    length = float(spec.get("length", 0.15))
    mod = target.modifiers.new(name="effect_hair", type="PARTICLE_SYSTEM")
    psys = mod.particle_system
    settings = psys.settings
    settings.type = "HAIR"
    settings.count = count
    settings.hair_length = length
    color = spec.get("color", [0.12, 0.08, 0.05, 1.0])
    ctx.bridge.push_event("effect.hair_color",
                          {"emitter": target.name, "color": color})
    return {"emitter": target.name, "count": count, "length": length}


# ---------------------------------------------------------------------------
# 10. 合成运动模糊（镜头 / 角色拖影）
# ---------------------------------------------------------------------------
def motion_blur(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    scene = bpy.context.scene
    enabled = bool(payload.get("enabled", True))
    factor = float(payload.get("factor", 0.5))
    ok = False
    try:
        scene.use_nodes = True
        comp = scene.node_tree
        blur = next((n for n in comp.nodes if n.type == "MOTIONBLUR"), None)
        if blur is None:
            blur = comp.nodes.new("CompositorNodeMotionBlur")
            comp.links.new(comp.nodes.get("Render Layers").outputs["Image"],
                           blur.inputs["Image"])
            comp.links.new(blur.outputs["Image"],
                           comp.nodes.get("Composite").inputs["Image"])
        blur.shutter = factor
        ok = True
    except (RuntimeError, TypeError, AttributeError):
        ok = False
    scene.render.use_motion_blur = enabled
    return {"enabled": enabled, "factor": factor, "compositor": ok}


def register(dispatcher) -> None:
    dispatcher.register("effect.particle", particle, ["object"])
    dispatcher.register("effect.glow", glow, ["object"])
    dispatcher.register("effect.fluid", fluid, ["object"])
    dispatcher.register("effect.deform", deform, ["object"])
    dispatcher.register("effect.camera_match", camera_match)
    dispatcher.register("effect.force_field", force_field, ["object"])
    dispatcher.register("effect.light", light)
    dispatcher.register("effect.world", world)
    dispatcher.register("effect.hair", hair, ["object"])
    dispatcher.register("effect.motion_blur", motion_blur)
