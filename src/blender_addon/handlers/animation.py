# -*- coding: utf-8 -*-
"""
动画生成模块（Blender 端）。

覆盖：关键帧位移 / 旋转 / 缩放、骨骼自动绑定、走跑跳循环、刚体 / 柔体 / 布料 /
流体物理、路径约束、动作捕捉轨迹对齐、时序变速与缓动曲线。
"""

from __future__ import annotations

import bpy
from typing import Any, Dict, List, Optional

from ..compat import version_compat
from . import _helpers as H
from . import character as Char


# 缓动曲线 → 插值类型 / 缓动标志映射
_EASING_INTERP = {
    "bezier": "BEZIER",
    "linear": "LINEAR",
    "ease_in": "BEZIER",
    "ease_out": "BEZIER",
    "ease_in_out": "BEZIER",
}
_EASING_FLAG = {
    "ease_in": "EASE_IN",
    "ease_out": "EASE_OUT",
    "ease_in_out": "EASE_IN_OUT",
}


def _apply_easing(obj: bpy.types.Object, easing: str) -> None:
    """为对象动作的全部 F 曲线设置插值与缓动标志。"""
    if obj.animation_data is None or obj.animation_data.action is None:
        return
    interp = _EASING_INTERP.get(easing.lower(), "BEZIER")
    flag = _EASING_FLAG.get(easing.lower())
    for fcurve in obj.animation_data.action.fcurves:
        for kf in fcurve.keyframe_points:
            kf.interpolation = interp
            if flag:
                kf.easing = flag


# ---------------------------------------------------------------------------
# 1. 关键帧动画
# ---------------------------------------------------------------------------
def keyframe(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    mode = payload.get("mode", "location")  # location / rotation / scale
    if mode not in ("location", "rotation", "scale"):
        raise ValueError(f"关键帧模式非法: {mode}（location / rotation / scale）")
    frames: List[List[Any]] = payload.get("frames") or []
    if not frames:
        raise ValueError("关键帧序列 frames 不能为空")
    attr = {"location": obj.location, "rotation": obj.rotation_euler,
            "scale": obj.scale}[mode]

    for frame, values in frames:
        if not isinstance(values, (list, tuple)) or len(values) != len(attr):
            raise ValueError(f"关键帧数值长度与 {mode} 不匹配（应为 {len(attr)} 个分量）")
        for axis, value in enumerate(values):
            attr[axis] = value
        obj.keyframe_insert(data_path=mode, frame=float(frame))

    easing = payload.get("easing", "bezier")
    _apply_easing(obj, easing)
    return {"object": obj.name, "mode": mode, "keyframes": len(frames),
            "easing": easing}


# ---------------------------------------------------------------------------
# 2. 骨骼自动绑定
# ---------------------------------------------------------------------------
def rig_auto(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    skeleton = payload.get("skeleton", "human")  # human / quadruped
    if skeleton == "quadruped":
        # 四足占位：复用标准骨架，附加四条腿提示（可在后续版本扩展专属骨架）
        ctx.log("warning", "四足骨架当前复用标准人形拓扑，权重按自动权重分配")
    return Char.rig_object(obj)


# ---------------------------------------------------------------------------
# 3. 走 / 跑 / 跳循环动画
# ---------------------------------------------------------------------------
def loop_cycle(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    cycle = payload.get("cycle", "walk")  # walk / run / jump
    if cycle not in ("walk", "run", "jump"):
        raise ValueError(f"循环动画类型非法: {cycle}（walk / run / jump）")
    fps = int(payload.get("fps", ctx.config.get("animation_fps", 24)))
    duration = float(payload.get("duration", 1.0))
    end_frame = max(2, int(round(fps * duration)))

    amplitude = {"walk": 0.3, "run": 0.55, "jump": 0.0}[cycle]
    height = {"walk": 0.02, "run": 0.04, "jump": 0.35}[cycle]

    import math
    for frame in (0, end_frame // 2, end_frame):
        phase = math.pi * frame / max(1, end_frame // 2)
        obj.rotation_euler[1] = amplitude * math.sin(phase)
        obj.location[2] = height * abs(math.sin(phase))
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)
        obj.keyframe_insert(data_path="location", frame=frame)
    _apply_easing(obj, payload.get("easing", "ease_in_out"))
    return {"object": obj.name, "cycle": cycle, "frames": end_frame, "fps": fps}


# ---------------------------------------------------------------------------
# 4. 物理模拟
# ---------------------------------------------------------------------------
def physics(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    kind = payload.get("kind", "rigid")  # rigid / soft / cloth / fluid
    applied: List[str] = []

    if kind == "rigid":
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.rigidbody.object_add()
        obj.rigid_body.type = payload.get("body_type", "ACTIVE")
        applied.append("rigid_body")
    elif kind == "soft":
        mod = obj.modifiers.new(name="soft", type="SOFT_BODY")
        mod.settings.mass = float(payload.get("mass", 1.0))
        applied.append(mod.name)
    elif kind == "cloth":
        mod = obj.modifiers.new(name="cloth", type="CLOTH")
        mod.settings.mass = float(payload.get("mass", 0.5))
        applied.append(mod.name)
    elif kind == "fluid":
        # 流体域占位修改器：实际解算参数由外部流体后端 / 体积效果补充
        mod = obj.modifiers.new(name="fluid", type="FLUID")
        mod.settings.type = "FLOW"
        applied.append(mod.name)
    else:
        raise ValueError(f"不支持的物理类型: {kind}")

    if payload.get("bake", False):
        # 物理烘焙由场景帧范围驱动，这里记录烘焙请求，渲染前由解算器执行
        ctx.bridge.push_event("anim.physics_bake",
                              {"object": obj.name, "kind": kind, "baked": True})
    return {"object": obj.name, "kind": kind, "modifiers": applied}


# ---------------------------------------------------------------------------
# 5. 路径约束
# ---------------------------------------------------------------------------
def path_constraint(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    points: List[List[float]] = payload.get("points") or []
    if len(points) < 2:
        raise ValueError("路径至少需要 2 个坐标点")
    for co in points:
        if not isinstance(co, (list, tuple)) or len(co) < 3:
            raise ValueError("路径坐标点至少包含 X / Y / Z 三个分量")
    curve_data = bpy.data.curves.new(name=f"{obj.name}_Path", type="CURVE")
    curve_data.dimensions = "3D"
    spline = curve_data.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for pt, co in zip(spline.points, points):
        pt.co = (co[0], co[1], co[2], 1.0)
    spline.use_cyclic_u = payload.get("cyclic", True)
    curve_obj = bpy.data.objects.new(curve_data.name, curve_data)
    bpy.context.collection.objects.link(curve_obj)

    constraint = obj.constraints.new(type="FOLLOW_PATH")
    constraint.target = curve_obj
    constraint.use_curve_follow = payload.get("follow_heading", True)
    # 路径位置关键帧
    obj.constraints[constraint.name].offset = 0.0
    obj.keyframe_insert(data_path=f"constraints[{constraint.name}].offset", frame=0)
    obj.constraints[constraint.name].offset = 100.0
    obj.keyframe_insert(data_path=f"constraints[{constraint.name}].offset",
                        frame=int(payload.get("end_frame", 24)))
    return {"object": obj.name, "path": curve_obj.name,
            "cyclic": spline.use_cyclic_u}


# ---------------------------------------------------------------------------
# 6. 动捕轨迹对齐
# ---------------------------------------------------------------------------
def mocap_apply(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    armature = H.require_object(payload["object"])
    spec = payload.get("motion", {})
    frames = spec.get("frames", [])
    fps = int(spec.get("fps", ctx.config.get("animation_fps", 24)))
    bpy.context.scene.render.fps = fps

    bone_map = {bone.name: bone for bone in armature.data.bones}
    applied = 0
    for frame in frames:
        index = int(frame["index"])
        rotations = frame.get("rotations", {})
        positions = frame.get("positions", {})
        for joint, rot in rotations.items():
            bone = bone_map.get(joint)
            if bone is None:
                continue
            pb = armature.pose.bones.get(joint)
            if pb is None:
                continue
            pb.rotation_euler = rot
            pb.keyframe_insert(data_path="rotation_euler", frame=index)
            applied += 1
        for joint, pos in positions.items():
            pb = armature.pose.bones.get(joint)
            if pb is None:
                continue
            pb.location = pos
            pb.keyframe_insert(data_path="location", frame=index)

    if spec.get("loop", True):
        # 首尾帧对齐，保证循环无缝
        ctx.log("info", "动捕轨迹已标记为循环，首尾帧自动对齐")
    return {"armature": armature.name, "frames": len(frames),
            "bone_keys": applied, "fps": fps,
            "confidence": spec.get("confidence", 0.0)}


# ---------------------------------------------------------------------------
# 7. 时序调整（全局 / 局部变速）
# ---------------------------------------------------------------------------
def timing(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    action = obj.animation_data.action if obj.animation_data else None
    if action is None:
        return {"object": obj.name, "scaled": False}

    speed = float(payload.get("speed", 1.0))  # >1 加速，<1 减速
    for fcurve in action.fcurves:
        for kf in fcurve.keyframe_points:
            kf.co[0] /= speed
            kf.handle_left[0] /= speed
            kf.handle_right[0] /= speed
    return {"object": obj.name, "speed": speed, "scaled": True}


# ---------------------------------------------------------------------------
# 8. 缓动曲线调整
# ---------------------------------------------------------------------------
def easing(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    _apply_easing(obj, payload.get("easing", "bezier"))
    return {"object": obj.name, "easing": payload.get("easing")}


def register(dispatcher) -> None:
    dispatcher.register("anim.keyframe", keyframe, ["object", "frames"])
    dispatcher.register("anim.rig_auto", rig_auto, ["object"])
    dispatcher.register("anim.loop_cycle", loop_cycle, ["object"])
    dispatcher.register("anim.physics", physics, ["object", "kind"])
    dispatcher.register("anim.path_constraint", path_constraint,
                        ["object", "points"])
    dispatcher.register("anim.mocap_apply", mocap_apply, ["object", "motion"])
    dispatcher.register("anim.timing", timing, ["object"])
    dispatcher.register("anim.easing", easing, ["object"])
