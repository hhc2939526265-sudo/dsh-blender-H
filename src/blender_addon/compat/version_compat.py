# -*- coding: utf-8 -*-
"""
Blender 版本兼容层（4.2 LTS ~ 5.3）。

集中处理不同版本之间 Python API 的差异：
- 渲染引擎标识
- Principled BSDF 节点输入插槽命名
- 模式切换 / 选择 API
- 低版本自动降级不支持的功能

业务代码一律通过本模块访问存在版本差异的 API，禁止直接写死插槽名。
"""

from __future__ import annotations

import bpy

# ---------------------------------------------------------------------------
# 版本探测
# ---------------------------------------------------------------------------
VERSION = bpy.app.version                       # 形如 (4, 2, 1)
VERSION_MAJOR = VERSION[0]
VERSION_MINOR = VERSION[1]
IS_4X = VERSION_MAJOR >= 4
IS_5X = VERSION_MAJOR >= 5
SUPPORTED_RANGE = ((4, 2), (5, 3))


def version_text() -> str:
    """返回人类可读的 Blender 版本号。"""
    return ".".join(str(v) for v in VERSION[:3])


def is_supported() -> bool:
    """判断当前 Blender 版本是否在支持范围内。"""
    return SUPPORTED_RANGE[0] <= VERSION[:2] <= SUPPORTED_RANGE[1]


# ---------------------------------------------------------------------------
# 渲染引擎兼容
# ---------------------------------------------------------------------------
# 各版本渲染引擎标识映射；入参为业务层统一使用的逻辑名
_ENGINE_MAP = {
    "EEVEE": "BLENDER_EEVEE",
    "CYCLES": "CYCLES",
    "BLENDER_EEVEE": "BLENDER_EEVEE",
}


def engine_id(logical_name: str) -> str:
    """
    将逻辑渲染引擎名转换为当前版本可用的引擎标识。

    :param logical_name: EEVEE / CYCLES（兼容历史大写写法）
    :return: bpy 场景可用的 engine 标识
    """
    return _ENGINE_MAP.get(str(logical_name).upper(), "BLENDER_EEVEE")


# ---------------------------------------------------------------------------
# 材质节点插槽兼容
# ---------------------------------------------------------------------------
# Principled BSDF 输入插槽在 3.x / 4.x 的命名差异，按候选名顺序解析
_PRINCIPLED_INPUT_CANDIDATES = {
    "base_color": ["Base Color"],
    "metallic": ["Metallic"],
    "roughness": ["Roughness"],
    "ior": ["IOR"],
    "alpha": ["Alpha"],
    "normal": ["Normal"],
    "specular": ["Specular IOR Level", "Specular"],
    "emission": ["Emission Color", "Emission"],
    "emission_strength": ["Emission Strength"],
}


def get_principled_input(bsdf_node, logical_key: str):
    """
    按候选名列表在 Principled BSDF 节点上解析输入插槽。

    :param bsdf_node: ShaderNodeBsdfPrincipled 节点
    :param logical_key: 逻辑键（base_color / metallic / roughness ...）
    :return: 插槽 Socket，未找到返回 None
    """
    candidates = _PRINCIPLED_INPUT_CANDIDATES.get(logical_key, [])
    for name in candidates:
        socket = bsdf_node.inputs.get(name)
        if socket is not None:
            return socket
    return None


def set_principled_input(bsdf_node, logical_key: str, value) -> bool:
    """
    安全写入 Principled BSDF 输入插槽；插槽不存在时静默降级。

    :return: 是否成功写入
    """
    socket = get_principled_input(bsdf_node, logical_key)
    if socket is None:
        return False
    try:
        socket.default_value = value
        return True
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# 场景 / 对象操作兼容
# ---------------------------------------------------------------------------
def set_active(obj) -> None:
    """跨版本安全设置活动对象并选中。"""
    bpy.ops.object.select_all(action="DESELECT")
    if obj is not None:
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj


def enter_object_mode() -> None:
    """确保处于 Object 模式（处于编辑 / 姿态模式时先切回）。"""
    if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
        try:
            bpy.ops.object.mode_set(mode="OBJECT")
        except RuntimeError:
            pass


def apply_modifier(obj, modifier_name: str) -> bool:
    """跨版本安全应用修改器。"""
    set_active(obj)
    try:
        bpy.ops.object.modifier_apply(modifier=modifier_name)
        return True
    except (RuntimeError, TypeError):
        return False


def shade_smooth(obj) -> None:
    """跨版本平滑着色。"""
    if obj.type == "MESH":
        for poly in obj.data.polygons:
            poly.use_smooth = True


def triangulate_if_needed(obj) -> None:
    """低版本拓扑兜底：必要时保留三角化修改器，不强制应用。"""
    # 预留降级钩子：4.x 几何节点不可用时回退到修改器方案
    return None
