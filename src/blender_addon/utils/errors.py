# -*- coding: utf-8 -*-
"""
参数校验异常与基础校验工具（纯标准库，不依赖 bpy）。

处理器里的参数校验统一抛 :class:`ParamError`，由 ``core.dispatcher`` 转成
E_PARAM 回执；校验提示一律使用中文并指名具体参数，禁止把原生
``ValueError`` / ``TypeError`` / ``AttributeError`` 泄漏成 E_EXEC。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

_MISSING = object()


class ParamError(ValueError):
    """参数不合法：dispatcher 会把它转成 E_PARAM 回执。"""


def _type_name(value: Any) -> str:
    return type(value).__name__


def _is_finite(value: float) -> bool:
    """判断浮点数是否为有限值（排除 NaN / 正负无穷）。"""
    return value == value and value not in (float("inf"), float("-inf"))


# ---------------------------------------------------------------- 基础类型
def require_str(value: Any, param: str) -> str:
    """要求字符串，否则抛 ParamError。"""
    if not isinstance(value, str):
        raise ParamError(f"{param} 需为字符串，收到 {_type_name(value)}")
    return value


def require_list(value: Any, param: str, min_len: int = 0,
                 max_len: Optional[int] = None) -> List[Any]:
    """要求列表 / 元组，否则抛 ParamError；可选长度约束。"""
    if not isinstance(value, (list, tuple)):
        raise ParamError(f"{param} 需为列表，收到 {_type_name(value)}")
    items = list(value)
    if len(items) < min_len:
        raise ParamError(f"{param} 至少需要 {min_len} 项，收到 {len(items)} 项")
    if max_len is not None and len(items) > max_len:
        raise ParamError(f"{param} 最多允许 {max_len} 项，收到 {len(items)} 项")
    return items


def require_str_list(value: Any, param: str,
                     min_len: int = 0) -> List[str]:
    """要求「字符串列表」，元素必须是 str。"""
    items = require_list(value, param, min_len)
    for index, item in enumerate(items):
        if not isinstance(item, str):
            raise ParamError(
                f"{param} 第 {index} 项需为字符串，收到 {_type_name(item)}")
    return items


def require_dict(value: Any, param: str) -> Dict[str, Any]:
    """要求字典 / 映射对象。"""
    if not isinstance(value, dict):
        raise ParamError(f"{param} 需为对象，收到 {_type_name(value)}")
    return value


def as_int(value: Any, param: str) -> int:
    """整数转换；不可转换（含字符串无法解析）时抛 ParamError。"""
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not _is_finite(value):
            raise ParamError(f"{param} 需为有限数字，收到 {value!r}")
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text, 10)
        except (TypeError, ValueError) as exc:
            raise ParamError(
                f"{param} 需为整数，收到的值无法解析: {value!r}") from exc
    raise ParamError(f"{param} 需为整数，收到 {_type_name(value)}")


def as_float(value: Any, param: str) -> float:
    """浮点转换；不可转换（含字符串无法解析）时抛 ParamError。"""
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        try:
            result = float(value.strip())
        except (TypeError, ValueError) as exc:
            raise ParamError(
                f"{param} 需为数字，收到的值无法解析: {value!r}") from exc
    else:
        raise ParamError(f"{param} 需为数字，收到 {_type_name(value)}")
    if not _is_finite(result):
        raise ParamError(f"{param} 需为有限数字，收到 {value!r}")
    return result


def as_bool(value: Any, param: str) -> bool:
    """布尔转换；仅接受 bool 与 0 / 1，其余类型（含字符串）抛 ParamError。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise ParamError(f"{param} 需为布尔值，收到 {_type_name(value)}")


def require_vec3(value: Any, param: str) -> List[float]:
    """要求长度 3 的数字数组（位置 / 旋转 / 缩放 / 坐标点）。"""
    items = require_list(value, param)
    if len(items) != 3:
        raise ParamError(f"{param} 需为 3 个分量的数组，收到 {len(items)} 个")
    return [as_float(item, f"{param}[{index}]")
            for index, item in enumerate(items)]


def require_float_list(value: Any, param: str,
                       min_len: int = 0) -> List[float]:
    """要求数字数组，返回 float 列表。"""
    items = require_list(value, param, min_len)
    return [as_float(item, f"{param}[{index}]")
            for index, item in enumerate(items)]


# ------------------------------------------------------------ payload 读取
def get_str(payload: Dict[str, Any], key: str,
            default: Optional[str] = None) -> Optional[str]:
    """读取字符串参数；缺省 / null 返回 default，类型不符抛 ParamError。"""
    value = payload.get(key, _MISSING)
    if value is _MISSING or value is None:
        return default
    return require_str(value, key)


def get_int(payload: Dict[str, Any], key: str, default: int = 0) -> int:
    """读取整数参数；缺省 / null 返回 default，不可转换抛 ParamError。"""
    value = payload.get(key, _MISSING)
    if value is _MISSING or value is None:
        return default
    return as_int(value, key)


def get_float(payload: Dict[str, Any], key: str, default: float = 0.0) -> float:
    """读取数字参数；缺省 / null 返回 default，不可转换抛 ParamError。"""
    value = payload.get(key, _MISSING)
    if value is _MISSING or value is None:
        return default
    return as_float(value, key)


def get_bool(payload: Dict[str, Any], key: str, default: bool = False) -> bool:
    """读取布尔参数；缺省 / null 返回 default，类型不符抛 ParamError。"""
    value = payload.get(key, _MISSING)
    if value is _MISSING or value is None:
        return default
    return as_bool(value, key)


def get_list(payload: Dict[str, Any], key: str, default: Any = None,
             min_len: int = 0) -> List[Any]:
    """读取列表参数；缺省 / null 返回 default（默认空列表）。"""
    value = payload.get(key, _MISSING)
    if value is _MISSING or value is None:
        return list(default) if default is not None else []
    return require_list(value, key, min_len)


def get_str_list(payload: Dict[str, Any], key: str, default: Any = None,
                 min_len: int = 0) -> List[str]:
    """读取字符串列表参数；缺省 / null 返回 default（默认空列表）。"""
    value = payload.get(key, _MISSING)
    if value is _MISSING or value is None:
        return list(default) if default is not None else []
    return require_str_list(value, key, min_len)


def get_dict(payload: Dict[str, Any], key: str,
             default: Any = None) -> Dict[str, Any]:
    """读取对象参数；缺省 / null 返回 default（默认空字典）。"""
    value = payload.get(key, _MISSING)
    if value is _MISSING or value is None:
        return dict(default) if default is not None else {}
    return require_dict(value, key)


def get_vec3(payload: Dict[str, Any], key: str,
             default: Any = None) -> Optional[List[float]]:
    """读取 3 分量向量参数；缺省 / null 返回 default。"""
    value = payload.get(key, _MISSING)
    if value is _MISSING or value is None:
        return default
    return require_vec3(value, key)


def get_float_list(payload: Dict[str, Any], key: str, default: Any = None,
                   min_len: int = 0) -> List[float]:
    """读取数字数组参数；缺省 / null 返回 default（默认空列表）。"""
    value = payload.get(key, _MISSING)
    if value is _MISSING or value is None:
        return list(default) if default is not None else []
    return require_float_list(value, key, min_len)
