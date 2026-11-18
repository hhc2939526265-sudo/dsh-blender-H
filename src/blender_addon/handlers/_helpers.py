# -*- coding: utf-8 -*-
"""处理器公共辅助函数。"""

from __future__ import annotations

import bpy
from typing import Any, Dict, List, Optional

from ..compat import version_compat


# 活动对象引用标识：自然语言解析等场景下目标对象未固定命名，统一以 "active" 指代
ACTIVE_REF = "active"


def _is_active_ref(name: str) -> bool:
    """判断入参是否为活动对象引用（空值 / "active" 均视为当前活动对象）。"""
    return name is None or str(name).strip().lower() == ACTIVE_REF


def get_object(name: str):
    """按名称取对象；``active`` 解析为当前活动对象，不存在返回 None。"""
    if _is_active_ref(name):
        return bpy.context.view_layer.objects.active
    return bpy.data.objects.get(name)


def require_object(name: str):
    """按名称取对象；``active`` 解析为当前活动对象，不存在则抛 KeyError。"""
    if _is_active_ref(name):
        obj = bpy.context.view_layer.objects.active
        if obj is None:
            raise KeyError("当前没有活动对象，请先在场景中选中目标对象")
        return obj
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise KeyError(f"对象不存在: {name}")
    return obj


def list_objects(names: Optional[List[str]]) -> List[bpy.types.Object]:
    """按名称列表解析对象，过滤不存在项。"""
    if not names:
        return list(bpy.context.selected_objects)
    return [o for n in names if (o := bpy.data.objects.get(n)) is not None]


def apply_transform(obj: bpy.types.Object) -> None:
    """应用对象的位置 / 旋转 / 缩放。"""
    version_compat.set_active(obj)
    try:
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    except RuntimeError:
        pass


def set_transform(obj: bpy.types.Object, payload: Dict[str, Any]) -> None:
    """从参数体写入位置 / 旋转 / 缩放。"""
    if "location" in payload:
        obj.location = payload["location"]
    if "rotation" in payload:
        obj.rotation_euler = payload["rotation"]
    if "scale" in payload:
        obj.scale = payload["scale"]


def unique_name(base: str) -> str:
    """生成不与现有对象冲突的名称。"""
    if base not in bpy.data.objects:
        return base
    idx = 1
    while f"{base}.{idx:03d}" in bpy.data.objects:
        idx += 1
    return f"{base}.{idx:03d}"


def add_modifier(obj: bpy.types.Object, mod_type: str, name: str):
    """添加修改器并返回。"""
    return obj.modifiers.new(name=name, type=mod_type)


def deselect_all() -> None:
    bpy.ops.object.select_all(action="DESELECT")
