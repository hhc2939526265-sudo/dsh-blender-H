# -*- coding: utf-8 -*-
"""
第三方 Blender 插件识别与调用模块（Blender 端）。

能力概览：
- 枚举当前会话中已启用的第三方 Addon，读取其 ``bl_info`` 元信息
- 按类别 / 描述关键词把插件归类到建模 / 绑定 / 动画 / 特效 / 材质 / 渲染 / 资产 / 导入导出
- 发现插件注册的 Operator（算子），提取算子 ID、标签与参数定义
- 提供安全的通用算子调用入口：执行前校验算子存在性与参数类型，异常全部收敛为回执
- 自然语言意图匹配：按关键词命中度为插件打分，返回最贴合的插件及其可用算子

说明：
- 仅扫描「已启用」的插件；未启用插件的算子未注册到 bpy.ops，无法安全调用。
- 算子发现基于 ``bpy.types.Operator`` 子类递归遍历，按算子 ID 前缀归属到对应插件；
  不同插件的命名空间若与本规则冲突，可在 detail 结果中人工核对。
- 本模块不读取第三方插件源码做语义分析；能力识别以 bl_info 元信息 + 关键词分类为准，
  后续可在 AI 适配层接入大模型对描述做进一步理解。
"""

from __future__ import annotations

import re
import sys
from typing import Any, Dict, List, Optional, Tuple

import bpy

from . import addon_catalog
from ..utils.errors import (ParamError, as_bool, as_float, as_int, get_dict,
                            get_int, get_str, get_str_list, require_float_list,
                            require_str)

# ---------------------------------------------------------------------------
# 能力分类关键词表（可在配置中扩展，禁止把魔法字符串散落到调用处）
# ---------------------------------------------------------------------------
CAPABILITY_KEYWORDS: Dict[str, List[str]] = {
    "modeling": ["model", "mesh", "topolog", "retopo", "boolean", "sculpt",
                 "remesh", "建模", "网格", "拓扑", "雕刻", "布线"],
    "rigging": ["rig", "armature", "bone", "weight", "skin", "skeleton",
                "绑定", "骨骼", "权重", "蒙皮"],
    "animation": ["anim", "motion", "keyframe", "action", "walk", "cycle",
                  "动画", "动作", "步态", "关键帧"],
    "effects": ["particle", "fluid", "smoke", "cloth", "vfx", "effect",
                "simulation", "粒子", "流体", "烟雾", "布料", "特效", "火花"],
    "material": ["material", "texture", "shader", "pbr", "node",
                 "材质", "贴图", "着色", "纹理"],
    "render": ["render", "engine", "light", "camera", "composit",
               "渲染", "灯光", "相机", "合成"],
    "asset": ["asset", "library", "pack", "kit", "scatter", "procedural",
              "资产", "模型库", "素材", "散布"],
    "io": ["importer", "exporter", "io", "fbx", "gltf", "glb", "obj",
           "import", "export", "导入", "导出"],
}

# 类别名（bl_info.category）到能力的兜底映射（通用 3D View 不归入具体能力）
CATEGORY_FALLBACK: Dict[str, str] = {
    "mesh": "modeling",
    "rigging": "rigging",
    "animation": "animation",
    "render": "render",
    "material": "material",
    "import-export": "io",
}

# 仅允许透传给算子的参数值类型（JSON 原始类型 + 原始类型数组）
_ALLOWED_SCALAR = (str, int, float, bool)
_ALLOWED_CONTAINER = (list, tuple)

# 本桥接插件自身的标识，枚举时排除，避免把自己列为第三方插件
_SELF_MARKERS = ("dsh", "bridge")

# 插件模块名合法字符：字母 / 数字 / 下划线 / 点号（子包），禁止路径分隔符与空格
_MODULE_NAME_RE = re.compile(r"^[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)*$")


# ===========================================================================
# 纯函数部分（不依赖 bpy，便于单元测试）
# ===========================================================================
def classify_addon(name: str, description: str, category: str = "") -> str:
    """
    根据名称 / 描述 / 类别关键词判定插件能力分类。

    :return: 能力标识（见 CAPABILITY_KEYWORDS 键），无法判定返回 ``other``
    """
    haystack = " ".join([name or "", description or "", category or ""]).lower()
    scores: Dict[str, int] = {}
    for capability, keywords in CAPABILITY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in haystack)
        if score:
            scores[capability] = score
    if scores:
        return max(scores, key=scores.get)
    fallback = CATEGORY_FALLBACK.get((category or "").strip().lower())
    return fallback or "other"


def _tokenize(text: str) -> List[str]:
    """极简分词：英文按非字母数字切分；中文输出单字与相邻二字词。"""
    text = (text or "").lower()
    tokens: List[str] = []
    latin_buf = ""
    cjk_buf = ""

    def flush_latin() -> None:
        nonlocal latin_buf
        if latin_buf:
            tokens.append(latin_buf)
            latin_buf = ""

    def flush_cjk() -> None:
        nonlocal cjk_buf
        if cjk_buf:
            for ch in cjk_buf:
                tokens.append(ch)
            for i in range(len(cjk_buf) - 1):
                tokens.append(cjk_buf[i:i + 2])
            cjk_buf = ""

    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            flush_latin()
            cjk_buf += ch
        elif ch.isalnum():
            flush_cjk()
            latin_buf += ch
        else:
            flush_latin()
            flush_cjk()
    flush_latin()
    flush_cjk()
    return tokens


def match_score(intent: str, addon: Dict[str, Any]) -> Tuple[int, List[str]]:
    """
    计算意图与插件元信息的匹配度。

    :return: (分数, 命中关键词列表)
    """
    intent_tokens = _tokenize(intent)
    if not intent_tokens:
        return 0, []
    haystack = " ".join([
        addon.get("name", ""), addon.get("description", ""),
        addon.get("category", ""), addon.get("capability", ""),
        " ".join(addon.get("operator_labels", [])),
    ]).lower()
    matched: List[str] = []
    score = 0
    for tok in intent_tokens:
        if len(tok) < 2 and not ("\u4e00" <= tok <= "\u9fff"):
            continue
        if tok in haystack:
            score += 1
            matched.append(tok)
    return score, matched


def _version_to_str(version: Any) -> str:
    """bl_info 版本元组 / 列表转字符串。"""
    if isinstance(version, (tuple, list)):
        return ".".join(str(v) for v in version)
    return str(version) if version else ""


def _sanitize_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """过滤算子参数，仅保留 JSON 原始类型，拒绝对象 / 不可序列化值。"""
    cleaned: Dict[str, Any] = {}
    for key, value in params.items():
        if isinstance(value, _ALLOWED_SCALAR):
            cleaned[key] = value
        elif isinstance(value, _ALLOWED_CONTAINER) and all(
                isinstance(v, _ALLOWED_SCALAR) for v in value):
            cleaned[key] = list(value)
        else:
            raise ParamError(f"参数 {key} 类型不允许: {type(value).__name__}")
    return cleaned


def _check_operator_policy(idname: str, ctx) -> None:
    """算子安全策略：调用前统一过总开关、黑名单与白名单。"""
    if not bool(ctx.config.get("allow_addon_invoke", True)):
        raise PermissionError("第三方插件算子调用已在配置中关闭（allow_addon_invoke=False）")
    lower_id = idname.lower()
    denylist = [str(item).lower() for item in ctx.config.get("addon_operator_denylist", [])]
    if any(bad and bad in lower_id for bad in denylist):
        raise PermissionError(f"算子命中黑名单，禁止调用: {idname}")
    allowlist = [str(item).lower() for item in ctx.config.get("addon_operator_allowlist", [])]
    if allowlist and not any(lower_id.startswith(prefix) for prefix in allowlist):
        raise PermissionError(f"算子不在白名单内: {idname}")


def _check_module_policy(module: str, ctx) -> None:
    """模块前缀白名单校验：白名单为空表示不限前缀。"""
    allowlist = [str(item).lower() for item in ctx.config.get("addon_module_allowlist", [])]
    lower_module = module.lower()
    if allowlist and not any(lower_module.startswith(prefix) for prefix in allowlist):
        raise PermissionError(f"插件模块不在白名单内: {module}")


def _coerce_node_input(socket, value: Any) -> Any:
    """按节点输入槽类型做基础类型转换，类型不兼容抛 ParamError。"""
    socket_type = getattr(socket, "type", "VALUE")
    param = f"输入槽 {getattr(socket, 'name', '?')}"
    if socket_type in ("INT", "BOOLEAN"):
        return as_bool(value, param) if socket_type == "BOOLEAN" \
            else as_int(value, param)
    if socket_type in ("FLOAT", "VALUE"):
        return as_float(value, param)
    if socket_type == "STRING":
        return require_str(value, param)
    if socket_type in ("VECTOR", "COLOR"):
        return require_float_list(value, param, min_len=3)
    return value


def _validate_module_name(module: str) -> str:
    """校验插件模块名格式，拒绝路径穿越 / 非法字符。"""
    require_str(module, "module")
    module = module.strip()
    if not module:
        raise ParamError("插件模块名不能为空")
    if not _MODULE_NAME_RE.match(module):
        raise ParamError(f"插件模块名非法: {module}（仅允许字母 / 数字 / 下划线 / 点号）")
    return module


def _require_object(name: Any):
    """按名称取对象；``active`` 解析为当前活动对象，不存在抛 KeyError。"""
    if isinstance(name, str) and name.strip().lower() == "active":
        obj = bpy.context.view_layer.objects.active
        if obj is None:
            raise KeyError("当前没有活动对象，请先在场景中选中目标对象")
        return obj
    if name is None:
        # 显式拦截 None：bpy_prop_collection.get(None) 会从 Blender C API 抛出
        # 晦涩的 SystemError（"returned a result with an exception set"）
        raise ParamError("缺少必填参数: object")
    if not isinstance(name, str):
        raise ParamError(f"object 需为对象名称字符串，收到 {type(name).__name__}")
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise KeyError(f"对象不存在: {name}")
    return obj


# ===========================================================================
# bpy 枚举 / 发现 / 调用部分
# ===========================================================================
def _iter_operator_classes() -> List[type]:
    """递归遍历所有已注册的 Operator 子类。"""
    seen: set = set()
    result: List[type] = []

    def rec(cls: type) -> None:
        for sub in cls.__subclasses__():
            if id(sub) in seen:
                continue
            seen.add(id(sub))
            result.append(sub)
            rec(sub)

    rec(bpy.types.Operator)
    return result


def _operator_classes_by_prefix() -> Dict[str, List[Dict[str, str]]]:
    """按算子 ID 首段命名空间分组全部已注册算子。"""
    grouped: Dict[str, List[Dict[str, str]]] = {}
    for cls in _iter_operator_classes():
        bl_idname = getattr(cls, "bl_idname", "")
        if not bl_idname or "." not in bl_idname:
            continue
        prefix = bl_idname.split(".", 1)[0]
        grouped.setdefault(prefix, []).append({
            "idname": bl_idname,
            "label": getattr(cls, "bl_label", bl_idname),
            "options": list(getattr(cls, "bl_options", []) or []),
        })
    return grouped


def _is_self(module_name: str, bl_info: Dict[str, Any]) -> bool:
    """判断是否为桥接插件自身。"""
    name = (bl_info.get("name") or "").lower()
    mod = (module_name or "").lower()
    return any(m in name for m in _SELF_MARKERS) or any(m in mod for m in _SELF_MARKERS)


def _collect_addons(max_operators: int) -> List[Dict[str, Any]]:
    """枚举已启用第三方插件及其算子摘要。"""
    addons_pref = getattr(bpy.context.preferences, "addons", {})
    op_groups = _operator_classes_by_prefix()
    addons: List[Dict[str, Any]] = []

    for item in addons_pref:
        module_name = getattr(item, "module", "")
        bl_info: Dict[str, Any] = {}
        module = sys.modules.get(module_name)
        if module is not None:
            bl_info = getattr(module, "bl_info", {}) or {}
        if _is_self(module_name, bl_info):
            continue

        category = str(bl_info.get("category", ""))
        name = str(bl_info.get("name", module_name))
        description = str(bl_info.get("description", ""))
        capability = classify_addon(name, description, category)

        module_root = module_name.split(".", 1)[0]
        operators = op_groups.get(module_root, [])[:max_operators]

        addons.append({
            "module": module_name,
            "name": name,
            "author": str(bl_info.get("author", "")),
            "version": _version_to_str(bl_info.get("version")),
            "category": category,
            "support": str(bl_info.get("support", "")),
            "description": description,
            "doc_url": str(bl_info.get("doc_url", "")),
            "location": str(bl_info.get("location", "")),
            "capability": capability,
            "operator_count": len(op_groups.get(module_root, [])),
            "operators": operators,
            "operator_labels": [op["label"] for op in operators],
        })
    return addons


def list_addons(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """列出全部已启用第三方插件及其能力分类与算子摘要。"""
    max_ops = int(ctx.config.get("addon_max_operators_per_addon", 50))
    addons = _collect_addons(max_ops)

    grouped: Dict[str, List[str]] = {}
    for addon in addons:
        grouped.setdefault(addon["capability"], []).append(addon["module"])

    return {
        "total": len(addons),
        "capabilities": grouped,
        "addons": [
            {k: v for k, v in addon.items() if k not in ("operators", "operator_labels")}
            for addon in addons
        ],
    }


def detail_addon(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """查询单个插件的完整元信息与算子参数定义。"""
    module_name = require_str(payload["module"], "module")
    max_ops = int(ctx.config.get("addon_max_operators_per_addon", 50))
    addons = _collect_addons(max_ops)
    matched = next((a for a in addons if a["module"] == module_name), None)
    if matched is None:
        raise KeyError(f"插件未在已启用列表中: {module_name}")

    # 补充每个算子的参数定义
    enriched_ops: List[Dict[str, Any]] = []
    for op in matched["operators"]:
        enriched_ops.append({**op, "properties": _operator_properties(op["idname"])})
    matched["operators"] = enriched_ops
    return matched


def _resolve_operator(idname: str):
    """按 ``namespace.operator`` 解析 bpy.ops 上的可调用对象。"""
    if "." not in idname:
        raise KeyError(f"算子 ID 非法: {idname}（应为 namespace.operator）")
    head, tail = idname.split(".", 1)
    namespace = getattr(bpy.ops, head, None)
    if namespace is None:
        raise KeyError(f"算子命名空间不存在: {head}")
    op = getattr(namespace, tail, None)
    if op is None:
        raise KeyError(f"算子不存在: {idname}")
    return op


def _operator_properties(idname: str) -> List[Dict[str, Any]]:
    """读取算子参数定义（标识符 / 标签 / 类型 / 是否必填）。"""
    try:
        op = _resolve_operator(idname)
        rna = op.get_rna_type()
    except (KeyError, RuntimeError, AttributeError):
        return []
    props: List[Dict[str, Any]] = []
    skip = {"rna_type", "bl_idname"}
    for prop in rna.properties:
        if prop.identifier in skip:
            continue
        props.append({
            "name": prop.identifier,
            "label": prop.name,
            "type": prop.type,
            "required": bool(prop.is_required),
        })
    return props


def invoke_operator(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """
    通用算子调用入口。

    payload:
        operator  算子 ID（namespace.operator）
        params    算子关键字参数（仅 JSON 原始类型）
        mode      execute（默认）/ invoke（INVOKE_DEFAULT，弹出交互面板）
    """
    idname = require_str(payload["operator"], "operator")
    params = _sanitize_params(get_dict(payload, "params", {}))
    mode = get_str(payload, "mode", "execute")
    if mode not in ("execute", "invoke"):
        raise ParamError(f"调用模式非法: {mode}（execute / invoke）")

    # 算子安全策略：总开关 → 黑名单 → 白名单前缀
    _check_operator_policy(idname, ctx)

    op = _resolve_operator(idname)
    ctx.log("info", f"调用第三方插件算子: {idname}（{mode}）")
    if mode == "invoke":
        op("INVOKE_DEFAULT", **params)
    else:
        op(**params)
    return {"operator": idname, "mode": mode, "params": params, "called": True}


def match_addons(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """按自然语言意图匹配最贴合的已启用插件。"""
    intent = require_str(payload["intent"], "intent")
    top_n = get_int(payload, "top_n", 5)
    max_ops = int(ctx.config.get("addon_max_operators_per_addon", 50))
    addons = _collect_addons(max_ops)

    scored: List[Dict[str, Any]] = []
    for addon in addons:
        score, matched = match_score(intent, addon)
        if score <= 0:
            continue
        scored.append({
            "module": addon["module"],
            "name": addon["name"],
            "capability": addon["capability"],
            "description": addon["description"],
            "score": score,
            "matched": matched,
            "operators": addon["operators"],
        })
    scored.sort(key=lambda item: item["score"], reverse=True)
    return {"intent": intent, "matches": scored[:top_n], "count": len(scored),
            "catalog_hits": addon_catalog.catalog_match(intent, top_n=top_n)}


def catalog(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """查询常用插件目录：按能力分类 / 关键词过滤，返回推荐桥接指令。"""
    capability = get_str(payload, "capability")
    keyword = get_str(payload, "keyword")
    plugins = addon_catalog.query_catalog(capability, keyword)
    return {"total": len(plugins), "plugins": plugins}


# ---------------------------------------------------------------------------
# 运行时启停 / 状态自检 / 全局检索 / 批量套用 / 几何节点组挂载
# ---------------------------------------------------------------------------
def enable_addon(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """运行时启用指定第三方插件（无需重启 Blender）。"""
    if not bool(ctx.config.get("allow_addon_enable", True)):
        raise PermissionError("第三方插件启用已在配置中关闭（allow_addon_enable=False）")
    module = _validate_module_name(payload["module"])
    if _is_self(module, {}):
        raise PermissionError("禁止启停桥接插件自身")
    _check_module_policy(module, ctx)
    bpy.ops.preferences.addon_enable(module=module)
    ctx.log("info", f"已启用第三方插件: {module}")
    return {"module": module, "enabled": True}


def disable_addon(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """运行时禁用指定第三方插件。"""
    if not bool(ctx.config.get("allow_addon_disable", True)):
        raise PermissionError("第三方插件禁用已在配置中关闭（allow_addon_disable=False）")
    module = _validate_module_name(payload["module"])
    if _is_self(module, {}):
        raise PermissionError("禁止启停桥接插件自身")
    _check_module_policy(module, ctx)
    bpy.ops.preferences.addon_disable(module=module)
    ctx.log("info", f"已禁用第三方插件: {module}")
    return {"module": module, "enabled": False}


def status_addons(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """插件生态自检：已启用清单、版本与调用策略开关。"""
    prefs = getattr(bpy.context.preferences, "addons", {})
    enabled = sorted(getattr(item, "module", "") for item in prefs)
    return {
        "blender_version": getattr(bpy.app, "version_string", ""),
        "enabled_count": len(enabled),
        "enabled": enabled,
        "policy": {
            "allow_invoke": bool(ctx.config.get("allow_addon_invoke", True)),
            "allow_enable": bool(ctx.config.get("allow_addon_enable", True)),
            "allow_disable": bool(ctx.config.get("allow_addon_disable", True)),
            "allowlist": list(ctx.config.get("addon_operator_allowlist", [])),
            "denylist": list(ctx.config.get("addon_operator_denylist", [])),
        },
    }


def operator_search(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """跨全部已注册算子按关键词检索（ID / 标签），返回归属前缀与算子定义。"""
    keyword = (get_str(payload, "keyword", "") or "").strip().lower()
    if not keyword:
        raise ParamError("检索关键词 keyword 不能为空")
    top_n = get_int(payload, "top_n", 30)
    groups = _operator_classes_by_prefix()
    results: List[Dict[str, Any]] = []
    for prefix, ops in groups.items():
        for op in ops:
            if keyword in op["idname"].lower() or keyword in op["label"].lower():
                results.append({"prefix": prefix, **op})
    results.sort(key=lambda item: item["idname"])
    return {"keyword": keyword, "count": len(results),
            "operators": results[:top_n]}


def operator_batch(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """对一批对象依次套用同一算子，逐个隔离异常并回执成功 / 失败清单。"""
    idname = require_str(payload["operator"], "operator")
    object_refs = get_str_list(payload, "objects")
    if not object_refs:
        raise ParamError("objects 对象列表不能为空")
    params = _sanitize_params(get_dict(payload, "params", {}))
    per_object = get_dict(payload, "per_object", {})
    for key, value in per_object.items():
        if value is not None and not isinstance(value, dict):
            raise ParamError(
                f"per_object.{key} 需为对象，收到 {type(value).__name__}")

    _check_operator_policy(idname, ctx)
    op = _resolve_operator(idname)

    results: List[Dict[str, Any]] = []
    succeeded = 0
    for ref in object_refs:
        obj = _require_object(ref)
        own_params = {**params, **(per_object.get(obj.name) or {})}
        try:
            for other in bpy.context.selected_objects:
                other.select_set(False)
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            op(**own_params)
            results.append({"object": obj.name, "status": "SUCCESS"})
            succeeded += 1
        except Exception as exc:  # 单对象失败不中断整批，异常收敛进回执
            results.append({"object": obj.name, "status": "FAILED", "error": str(exc)})
    return {"operator": idname, "total": len(object_refs),
            "succeeded": succeeded, "results": results}


def nodegroup_apply(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """把已存在的几何节点组挂到对象上（来自资产库 / 已启用插件），可覆写输入。"""
    obj = _require_object(payload.get("object"))
    group_name = require_str(payload["node_group"], "node_group")
    node_group = bpy.data.node_groups.get(group_name)
    if node_group is None:
        raise KeyError(f"几何节点组不存在: {group_name}（请先由插件 / 资产库导入）")

    mod = obj.modifiers.new(name=f"{group_name}_GN", type="NODES")
    mod.node_group = node_group
    inputs = get_dict(payload, "inputs", {})
    applied_inputs: List[str] = []
    for socket_name, value in inputs.items():
        if socket_name in mod.inputs:
            socket = mod.inputs[socket_name]
            socket.default_value = _coerce_node_input(socket, value)
            applied_inputs.append(socket_name)
    return {"object": obj.name, "node_group": group_name,
            "modifier": mod.name, "inputs": applied_inputs}


def register(dispatcher) -> None:
    dispatcher.register("addon.list", list_addons)
    dispatcher.register("addon.detail", detail_addon, ["module"])
    dispatcher.register("addon.invoke", invoke_operator, ["operator"])
    dispatcher.register("addon.match", match_addons, ["intent"])
    dispatcher.register("addon.enable", enable_addon, ["module"])
    dispatcher.register("addon.disable", disable_addon, ["module"])
    dispatcher.register("addon.status", status_addons)
    dispatcher.register("addon.operator_search", operator_search, ["keyword"])
    dispatcher.register("addon.operator_batch", operator_batch, ["operator", "objects"])
    dispatcher.register("addon.nodegroup_apply", nodegroup_apply, ["node_group"])
    dispatcher.register("addon.catalog", catalog)
