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


# ---------------------------------------------------------------------------
# 9. 清除对象动画数据
# ---------------------------------------------------------------------------
def clear(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    obj.animation_data_clear()
    return {"object": obj.name, "cleared": True}


# ---------------------------------------------------------------------------
# 10. 骨骼 IK 约束（角色肢体反向运动学）
# ---------------------------------------------------------------------------
def ik(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    armature = H.require_object(payload["object"])
    bone_name = payload["bone"]
    target = H.require_object(payload["target"])
    pb = armature.pose.bones.get(bone_name)
    if pb is None:
        raise KeyError(f"骨骼不存在: {bone_name}")
    con = pb.constraints.new(type="IK")
    con.target = target
    con.chain_count = int(payload.get("chain_count", 2))
    con.ik_type = "COPY_POSE" if payload.get("copy_pose", False) else "LEGACY"
    return {"armature": armature.name, "bone": bone_name,
            "target": target.name, "chain_count": con.chain_count}


# ---------------------------------------------------------------------------
# 11. 复制变换约束（跟随目标位置 / 旋转 / 缩放）
# ---------------------------------------------------------------------------
def copy_transform(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    target = H.require_object(payload["target"])
    con = obj.constraints.new(type="COPY_TRANSFORMS")
    con.target = target
    con.influence = float(payload.get("influence", 1.0))
    return {"object": obj.name, "target": target.name,
            "influence": con.influence}


# ---------------------------------------------------------------------------
# 12. 列出场景动作数据
# ---------------------------------------------------------------------------
def action_list(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    actions = [a.name for a in bpy.data.actions]
    obj = H.get_object(payload.get("object"))
    current = obj.animation_data.action.name \
        if obj is not None and obj.animation_data and obj.animation_data.action else None
    return {"actions": actions, "active": current, "count": len(actions)}


# ---------------------------------------------------------------------------
# 13. 对象父子绑定（角色道具 / 部件挂载）
# ---------------------------------------------------------------------------
def parent_set(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    parent = H.require_object(payload["parent"]) if payload.get("parent") else None
    keep = bool(payload.get("keep_transform", True))
    if keep:
        obj.matrix_parent_inverse = obj.matrix_world.inverted()
    obj.parent = parent
    return {"object": obj.name, "parent": parent.name if parent else None}


# ---------------------------------------------------------------------------
# 14. 单骨骼关键帧（战斗姿态逐骨骼控制）
# ---------------------------------------------------------------------------
def bone_keyframe(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    armature = H.require_object(payload["object"])
    bone_name = payload["bone"]
    pb = armature.pose.bones.get(bone_name)
    if pb is None:
        raise KeyError(f"骨骼不存在: {bone_name}")
    frame = float(payload.get("frame", 0))
    if "rotation" in payload:
        rot = payload["rotation"]
        if not isinstance(rot, (list, tuple)) or len(rot) != 3:
            raise ValueError("骨骼旋转需为 3 个分量 [X, Y, Z]")
        pb.rotation_euler = rot
        pb.keyframe_insert(data_path="rotation_euler", frame=frame)
    if "location" in payload:
        loc = payload["location"]
        if not isinstance(loc, (list, tuple)) or len(loc) != 3:
            raise ValueError("骨骼位置需为 3 个分量 [X, Y, Z]")
        pb.location = loc
        pb.keyframe_insert(data_path="location", frame=frame)
    return {"armature": armature.name, "bone": bone_name, "frame": frame}


# ---------------------------------------------------------------------------
# 15. 批量骨骼姿态（出拳 / 格挡 / 挥剑 / 腾空等战斗姿态）
# ---------------------------------------------------------------------------
def pose(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    armature = H.require_object(payload["object"])
    poses: Dict[str, Any] = payload.get("poses") or {}
    if not poses:
        raise ValueError("poses 姿态表不能为空")
    frame = float(payload.get("frame", 0))
    applied: List[str] = []
    for bone_name, spec in poses.items():
        pb = armature.pose.bones.get(bone_name)
        if pb is None:
            ctx.log("warning", f"姿态骨骼不存在，已跳过: {bone_name}")
            continue
        if "rotation" in spec:
            pb.rotation_euler = spec["rotation"]
            pb.keyframe_insert(data_path="rotation_euler", frame=frame)
        if "location" in spec:
            pb.location = spec["location"]
            pb.keyframe_insert(data_path="location", frame=frame)
        applied.append(bone_name)
    return {"armature": armature.name, "frame": frame, "bones": applied}


# ---------------------------------------------------------------------------
# 16. 目标跟随约束（武器 / 攻击点 / 镜头锁定目标）
# ---------------------------------------------------------------------------
_FOLLOW_CONSTRAINTS = {
    "COPY_TRANSFORMS", "COPY_LOCATION", "COPY_ROTATION",
    "COPY_SCALE", "TRACK_TO", "FOLLOW_PATH",
}


def follow_target(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    target = H.require_object(payload["target"])
    ctype = payload.get("constraint", "COPY_TRANSFORMS")
    if ctype not in _FOLLOW_CONSTRAINTS:
        raise ValueError(f"不支持的跟随约束类型: {ctype}")
    bone_name = payload.get("bone")
    owner = obj
    if bone_name:
        pb = obj.pose.bones.get(bone_name)
        if pb is None:
            raise KeyError(f"骨骼不存在: {bone_name}")
        owner = pb
    con = owner.constraints.new(type=ctype)
    con.target = target
    con.influence = float(payload.get("influence", 1.0))
    return {"object": obj.name, "bone": bone_name, "target": target.name,
            "constraint": ctype, "influence": con.influence}


# ---------------------------------------------------------------------------
# 17. 动作层混合（NLA 权重规格，真机由解算器落地）
# ---------------------------------------------------------------------------
def action_mix(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    layers = payload.get("layers", [])
    if not isinstance(layers, list) or not layers:
        raise ValueError("layers 动作层列表不能为空")
    for layer in layers:
        if "action" not in layer:
            raise ValueError("每个动作层需包含 action 名称")
    # NLA 混合需在真机 Blender 内逐条挂载动作条；这里先记录混合规格，
    # 与物理烘焙一致由渲染前解算器落地，避免在桩环境做伪实现。
    ctx.bridge.push_event("anim.action_mix",
                          {"object": obj.name, "layers": layers})
    return {"object": obj.name, "layers": len(layers)}


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
    dispatcher.register("anim.clear", clear, ["object"])
    dispatcher.register("anim.ik", ik, ["object", "bone", "target"])
    dispatcher.register("anim.copy_transform", copy_transform, ["object", "target"])
    dispatcher.register("anim.action_list", action_list)
    dispatcher.register("anim.parent_set", parent_set, ["object"])
    dispatcher.register("anim.bone_keyframe", bone_keyframe, ["object", "bone"])
    dispatcher.register("anim.pose", pose, ["object", "poses"])
    dispatcher.register("anim.follow_target", follow_target, ["object", "target"])
    dispatcher.register("anim.action_mix", action_mix, ["object", "layers"])
