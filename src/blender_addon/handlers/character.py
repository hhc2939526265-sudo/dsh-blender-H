# -*- coding: utf-8 -*-
"""
图片驱动人物建模模块（Blender 端）。

链路：上传图片（分片落盘）→ AI 适配层解析角色规格 → 程序化装配标准化人体
（身体 / 服装分层 / 发型面片 / 面部形状键）→ 预处理（原点 / 法线 / UV / PBR）
→ 标准人形骨骼绑定与权重分配。

说明：真正的高精度人体重建依赖外部推理后端（见 ``ai/`` 层）；本模块在 Mock
兜底下生成拓扑规范、可二次编辑的标准人体占位资产，接入后端后仅替换规格数据来源，
装配与绑定流程不变。
"""

from __future__ import annotations

import bpy
import math
from typing import Any, Dict, List, Optional, Tuple

from ..compat import version_compat
from . import _helpers as H


# 精度档位 → 网格细分参数
_QUALITY_VERTICES = {"low": 12, "medium": 20, "high": 32}
_QUALITY_SUBSURF = {"low": 0, "medium": 1, "high": 2}


# ---------------------------------------------------------------------------
# 几何装配辅助
# ---------------------------------------------------------------------------
def _add_part(ptype: str, name: str, location: Tuple[float, ...],
              scale: Tuple[float, ...], quality: str) -> bpy.types.Object:
    """添加一个身体部件并返回对象。"""
    kwargs: Dict[str, Any] = {"location": location}
    if ptype == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=_QUALITY_VERTICES[quality], ring_count=16, **kwargs)
    elif ptype == "cylinder":
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=_QUALITY_VERTICES[quality], **kwargs)
    elif ptype == "cube":
        bpy.ops.mesh.primitive_cube_add(**kwargs)
    else:
        bpy.ops.mesh.primitive_cube_add(**kwargs)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    H.apply_transform(obj)
    return obj


def _join_objects(objects: List[bpy.types.Object], name: str) -> bpy.types.Object:
    """合并对象为一个网格。"""
    version_compat.deselect_all()
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    body = bpy.context.active_object
    body.name = name
    return body


def _average_image_color(image_path: str) -> Optional[List[float]]:
    """从图片像素提取平均 RGBA 颜色（无第三方依赖，走 Blender 图像 API）。"""
    if not image_path:
        return None
    try:
        image = bpy.data.images.load(image_path, check_existing=True)
        pixels = list(image.pixels)
        if not pixels:
            return None
        channel = 4
        r = g = b = a = 0.0
        n = len(pixels) // channel
        for i in range(n):
            r += pixels[i * channel]
            g += pixels[i * channel + 1]
            b += pixels[i * channel + 2]
            a += pixels[i * channel + 3]
        bpy.data.images.remove(image)
        return [r / n, g / n, b / n, a / n]
    except (OSError, RuntimeError, ValueError):
        return None


def _create_material(name: str, color: List[float], roughness: float,
                     metallic: float = 0.0, alpha: float = 1.0) -> bpy.types.Material:
    """创建基础 PBR 材质节点树。"""
    mat = bpy.data.materials.new(name=name)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    version_compat.set_principled_input(bsdf, "base_color", color)
    version_compat.set_principled_input(bsdf, "roughness", roughness)
    version_compat.set_principled_input(bsdf, "metallic", metallic)
    version_compat.set_principled_input(bsdf, "alpha", alpha)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    if alpha < 1.0:
        mat.surface_render_method = "BLENDED" if hasattr(mat, "surface_render_method") else "DITHERED"
    return mat


def _add_shape_keys(obj: bpy.types.Object, key_names: List[str]) -> int:
    """为网格添加 Basis 与一组面部形状键（确定性微小形变占位）。"""
    if obj.type != "MESH":
        return 0
    basis = obj.shape_key_add(name="Basis")
    count = 0
    for idx, key in enumerate(key_names):
        sk = obj.shape_key_add(name=key)
        # 按顶点索引做确定性微小偏移，保证形状键非空且可编辑
        for v_index, vert in enumerate(sk.data):
            co = basis.data[v_index].co
            phase = (idx + 1) * 0.13 + v_index * 0.017
            vert.co = (co.x + 0.004 * math.sin(phase),
                       co.y + 0.004 * math.cos(phase),
                       co.z + 0.004 * math.sin(phase * 1.3))
        count += 1
    return count


# ---------------------------------------------------------------------------
# 骨骼绑定
# ---------------------------------------------------------------------------
# 骨骼层级：子骨骼头部 = 父骨骼尾部
_BONES: List[Tuple[str, str, Tuple[float, float, float], Tuple[float, float, float]]] = [
    ("root", "", (0, 0, 0.0), (0, 0, 0.9)),
    ("hips", "root", (0, 0, 0.9), (0, 0, 1.05)),
    ("spine", "hips", (0, 0, 1.05), (0, 0, 1.2)),
    ("chest", "spine", (0, 0, 1.2), (0, 0, 1.38)),
    ("neck", "chest", (0, 0, 1.38), (0, 0, 1.46)),
    ("head", "neck", (0, 0, 1.46), (0, 0, 1.62)),
    ("left_clavicle", "chest", (-0.12, 0, 1.36), (-0.22, 0, 1.34)),
    ("left_upper_arm", "left_clavicle", (-0.22, 0, 1.34), (-0.30, 0, 1.12)),
    ("left_forearm", "left_upper_arm", (-0.30, 0, 1.12), (-0.32, 0, 0.92)),
    ("left_hand", "left_forearm", (-0.32, 0, 0.92), (-0.33, 0, 0.82)),
    ("right_clavicle", "chest", (0.12, 0, 1.36), (0.22, 0, 1.34)),
    ("right_upper_arm", "right_clavicle", (0.22, 0, 1.34), (0.30, 0, 1.12)),
    ("right_forearm", "right_upper_arm", (0.30, 0, 1.12), (0.32, 0, 0.92)),
    ("right_hand", "right_forearm", (0.32, 0, 0.92), (0.33, 0, 0.82)),
    ("left_thigh", "hips", (-0.11, 0, 0.9), (-0.12, 0, 0.55)),
    ("left_shin", "left_thigh", (-0.12, 0, 0.55), (-0.12, 0, 0.18)),
    ("left_foot", "left_shin", (-0.12, 0, 0.18), (-0.12, 0.08, 0.06)),
    ("toe_left", "left_foot", (-0.12, 0.08, 0.06), (-0.12, 0.18, 0.04)),
    ("right_thigh", "hips", (0.11, 0, 0.9), (0.12, 0, 0.55)),
    ("right_shin", "right_thigh", (0.12, 0, 0.55), (0.12, 0, 0.18)),
    ("right_foot", "right_shin", (0.12, 0, 0.18), (0.12, 0.08, 0.06)),
    ("toe_right", "right_foot", (0.12, 0.08, 0.06), (0.12, 0.18, 0.04)),
]


def build_armature(name: str) -> bpy.types.Object:
    """创建标准人形骨骼骨架（MetaHuman 兼容命名）。"""
    arm_data = bpy.data.armatures.new(name)
    arm_obj = bpy.data.objects.new(name, arm_data)
    bpy.context.collection.objects.link(arm_obj)
    version_compat.set_active(arm_obj)
    bpy.ops.object.mode_set(mode="EDIT")

    bones: Dict[str, bpy.types.EditBone] = {}
    for bone_name, parent, head, tail in _BONES:
        eb = arm_data.edit_bones.new(bone_name)
        eb.head = head
        eb.tail = tail
        if parent:
            eb.parent = bones[parent]
        bones[bone_name] = eb

    bpy.ops.object.mode_set(mode="OBJECT")
    return arm_obj


def rig_object(mesh_obj: bpy.types.Object, armature: Optional[bpy.types.Object] = None
               ) -> Dict[str, Any]:
    """为网格创建 / 复用骨架并执行自动权重绑定。"""
    if armature is None:
        armature = build_armature(H.unique_name("Character_Rig"))
    # 骨架置于网格层级下
    if mesh_obj.name not in armature.children:
        mesh_obj.parent = armature
    # 自动权重：先加骨架修改器，再用自动权重算子
    for mod in list(mesh_obj.modifiers):
        if mod.type == "ARMATURE":
            mesh_obj.modifiers.remove(mod)
    mesh_obj.modifiers.new(name="rig", type="ARMATURE").object = armature

    version_compat.deselect_all()
    mesh_obj.select_set(True)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    try:
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
        weighted = True
    except (RuntimeError, TypeError):
        weighted = False
    return {"armature": armature.name, "mesh": mesh_obj.name,
            "auto_weights": weighted, "bones": len(armature.data.bones)}


# ---------------------------------------------------------------------------
# 处理器
# ---------------------------------------------------------------------------
def build(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """图片驱动角色建模主入口。"""
    image_paths: List[str] = payload.get("image_paths", [])
    params = {"quality": payload.get("quality", ctx.config.get("mesh_quality", "medium")),
               "confidence": ctx.config.get("mocap_confidence", 0.6)}

    spec, provider_name = ctx.bridge.providers.safe_call(
        "analyze_character", image_paths, params)

    quality = spec.get("quality", "medium")
    quality = quality if quality in _QUALITY_VERTICES else "medium"
    proportions = spec.get("proportions", {})
    height = float(proportions.get("height", 1.75))
    scale_k = height / 1.75

    # 1) 装配身体部件
    parts: List[bpy.types.Object] = []
    parts.append(_add_part("cube", "pelvis", (0, 0, 0.92 * scale_k),
                           (0.16, 0.10, 0.12), quality))
    parts.append(_add_part("cube", "torso", (0, 0, 1.18 * scale_k),
                           (0.17, 0.11, 0.22), quality))
    parts.append(_add_part("sphere", "head", (0, 0, 1.52 * scale_k),
                           (0.10, 0.09, 0.12), quality))
    parts.append(_add_part("cylinder", "upper_arm_L", (-0.27, 0, 1.24 * scale_k),
                           (0.05, 0.05, 0.16), quality))
    parts.append(_add_part("cylinder", "upper_arm_R", (0.27, 0, 1.24 * scale_k),
                           (0.05, 0.05, 0.16), quality))
    parts.append(_add_part("cylinder", "forearm_L", (-0.29, 0, 1.0 * scale_k),
                           (0.04, 0.04, 0.14), quality))
    parts.append(_add_part("cylinder", "forearm_R", (0.29, 0, 1.0 * scale_k),
                           (0.04, 0.04, 0.14), quality))
    parts.append(_add_part("cylinder", "thigh_L", (-0.11, 0, 0.62 * scale_k),
                           (0.07, 0.07, 0.22), quality))
    parts.append(_add_part("cylinder", "thigh_R", (0.11, 0, 0.62 * scale_k),
                           (0.07, 0.07, 0.22), quality))
    parts.append(_add_part("cylinder", "shin_L", (-0.11, 0, 0.3 * scale_k),
                           (0.055, 0.055, 0.18), quality))
    parts.append(_add_part("cylinder", "shin_R", (0.11, 0, 0.3 * scale_k),
                           (0.055, 0.055, 0.18), quality))

    body = _join_objects(parts, H.unique_name("Character_Body"))

    # 2) 精度细分
    sub_level = _QUALITY_SUBSURF[quality]
    if sub_level > 0:
        mod = body.modifiers.new(name="subsurf", type="SUBSURF")
        mod.levels = sub_level
        mod.render_levels = sub_level

    # 3) 预处理：法线统一 / 原点归位 / UV 展开
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.uv.smart_project(angle_limit=66.0)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.origin_set(type="ORIGIN_GEOMETRY")

    # 4) 面部形状键
    key_count = _add_shape_keys(body, spec.get("shape_keys", []))

    # 5) 皮肤材质（优先从首图提取平均色）
    skin_color = spec.get("skin_color", [0.82, 0.66, 0.55, 1.0])
    if image_paths:
        avg = _average_image_color(image_paths[0])
        if avg:
            skin_color = avg
    skin_mat = _create_material("Skin_Mat", skin_color, roughness=0.55)
    body.data.materials.append(skin_mat)

    # 6) 服装分层（独立网格 + 独立材质）
    clothing_objs: List[str] = []
    for index, cloth in enumerate(spec.get("clothing", [])):
        part = cloth.get("part", f"cloth_{index}")
        col = cloth.get("color", [0.3, 0.3, 0.3, 1.0])
        mat = _create_material(f"Cloth_{part}", col,
                               roughness=float(cloth.get("roughness", 0.8)),
                               metallic=float(cloth.get("metallic", 0.0)))
        if part == "top":
            obj = _add_part("cube", f"Cloth_Top", (0, 0, 1.18 * scale_k),
                            (0.185, 0.125, 0.20), quality)
        elif part == "bottom":
            obj = _add_part("cube", f"Cloth_Bottom", (0, 0, 0.78 * scale_k),
                            (0.17, 0.115, 0.18), quality)
        else:
            obj = _add_part("cube", f"Cloth_{part}", (0, 0, 0.1 * scale_k),
                            (0.08, 0.12, 0.05), quality)
        obj.data.materials.append(mat)
        clothing_objs.append(obj.name)

    # 7) 发型面片（压扁球体置于头顶）
    hair = _add_part("sphere", "Hair", (0, -0.01, 1.6 * scale_k),
                     (0.105, 0.095, 0.07), quality)
    hair_mat = _create_material("Hair_Mat",
                                spec.get("hair", {}).get("color", [0.05, 0.04, 0.03, 1]),
                                roughness=0.7)
    hair.data.materials.append(hair_mat)

    # 8) 自动骨骼绑定
    rig_info = rig_object(body)

    return {
        "body": body.name,
        "clothing": clothing_objs,
        "hair": hair.name,
        "shape_keys": key_count,
        "vertices": len(body.data.vertices),
        "quality": quality,
        "provider": provider_name,
        "rig": rig_info,
        "proportions": proportions,
    }


def rig(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """对已有网格执行骨骼自动绑定。"""
    obj = H.require_object(payload["object"])
    return rig_object(obj)


def shape_keys(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """为指定网格批量写入面部形状键。"""
    obj = H.require_object(payload["object"])
    names = payload.get("shape_keys") or spec_default_keys()
    count = _add_shape_keys(obj, names)
    return {"object": obj.name, "shape_keys": count}


def uv_bake(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """从参考图提取颜色 / 粗糙度信息并写入基础 PBR 材质。"""
    obj = H.require_object(payload["object"])
    image_path = payload.get("image_path", "")
    color = _average_image_color(image_path) if image_path else None
    mat = _create_material(
        f"Baked_{obj.name}", color or [0.7, 0.7, 0.7, 1.0],
        roughness=float(payload.get("roughness", 0.7)),
        metallic=float(payload.get("metallic", 0.0)))
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    return {"object": obj.name, "material": mat.name,
            "color": list(mat.node_tree.nodes.get("Principled BSDF").inputs["Base Color"].default_value)
            if color else None}


def spec_default_keys() -> List[str]:
    """返回默认面部形状键清单。"""
    from ..ai.mock_adapter import FACE_SHAPE_KEYS
    return list(FACE_SHAPE_KEYS)


def register(dispatcher) -> None:
    dispatcher.register("character.build", build)
    dispatcher.register("character.rig", rig, ["object"])
    dispatcher.register("character.shape_keys", shape_keys, ["object"])
    dispatcher.register("character.uv_bake", uv_bake, ["object"])
