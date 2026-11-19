# -*- coding: utf-8 -*-
"""处理器公共辅助函数。"""

from __future__ import annotations

import bpy
from typing import Any, Dict, List, Optional

from ..compat import version_compat
from ..utils.errors import (ParamError, require_list, require_str, require_vec3)


# 活动对象引用标识：自然语言解析等场景下目标对象未固定命名，统一以 "active" 指代
ACTIVE_REF = "active"

# 变换参数：位置 / 旋转 / 缩放均为 3 分量
_TRANSFORM_KEYS = ("location", "rotation", "scale")


def _is_active_ref(name: Any) -> bool:
    """判断入参是否为活动对象引用（空值 / "active" 均视为当前活动对象）。"""
    return name is None or (isinstance(name, str)
                            and name.strip().lower() == ACTIVE_REF)


def _check_object_name(name: Any, param: str) -> None:
    """对象名必须是字符串（None / "active" 由调用处按活动对象解析）。"""
    if name is not None:
        require_str(name, param)


def get_object(name: Any, param: str = "object"):
    """按名称取对象；``active`` 解析为当前活动对象，不存在返回 None。"""
    _check_object_name(name, param)
    if _is_active_ref(name):
        return bpy.context.view_layer.objects.active
    return bpy.data.objects.get(name)


def require_object(name: Any, param: str = "object"):
    """按名称取对象；``active`` 解析为当前活动对象，不存在则抛 KeyError。"""
    _check_object_name(name, param)
    if _is_active_ref(name):
        obj = bpy.context.view_layer.objects.active
        if obj is None:
            raise KeyError("当前没有活动对象，请先在场景中选中目标对象")
        return obj
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise KeyError(f"对象不存在: {name}")
    return obj


def list_objects(names: Any, param: str = "objects") -> List[bpy.types.Object]:
    """按名称列表解析对象，过滤不存在项；空列表沿用当前选中对象。"""
    if names is None:
        return list(bpy.context.selected_objects)
    items = require_list(names, param)
    if not items:
        return list(bpy.context.selected_objects)
    for index, item in enumerate(items):
        if not isinstance(item, str):
            raise ParamError(
                f"{param} 第 {index} 项需为对象名称字符串，收到 "
                f"{type(item).__name__}")
    return [o for item in items if (o := bpy.data.objects.get(item)) is not None]


def get_datablock(collection: Any, name: Any, param: str):
    """在 bpy.data 集合里按名称查数据块；名称非字符串时抛 ParamError。"""
    require_str(name, param)
    return collection.get(name)


def apply_transform(obj: bpy.types.Object) -> None:
    """应用对象的位置 / 旋转 / 缩放。"""
    version_compat.set_active(obj)
    try:
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    except RuntimeError:
        pass


def set_transform(obj: bpy.types.Object, payload: Dict[str, Any]) -> None:
    """从参数体写入位置 / 旋转 / 缩放（均为 3 分量数字数组）。"""
    for key in _TRANSFORM_KEYS:
        if key in payload and payload[key] is not None:
            setattr(obj, key, require_vec3(payload[key], key))


def unique_name(base: Any, param: str = "name") -> str:
    """生成不与现有对象冲突的名称。"""
    require_str(base, param)
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
