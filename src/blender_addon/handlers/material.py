# -*- coding: utf-8 -*-
"""
PBR 材质与批量材质管理模块（Blender 端）。

- 提示词 / 参数驱动生成完整材质节点树（基础色 / 法线 / 粗糙度 / 金属度 / AO / 自发光）
- 批量替换、批量参数调整
- 材质预设保存 / 加载（JSON 持久化到用户预设目录）
"""

from __future__ import annotations

import os
import json
import bpy
from typing import Any, Dict, List, Optional

from ..compat import version_compat
from ..utils import paths
from . import _helpers as H


def _new_pbr_material(name: str) -> bpy.types.Material:
    mat = bpy.data.materials.new(name=name)
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def _apply_params(bsdf, params: Dict[str, Any]) -> None:
    """把材质参数写入 Principled 插槽（缺失项静默降级）。"""
    mapping = {
        "base_color": "base_color", "metallic": "metallic",
        "roughness": "roughness", "ior": "ior", "alpha": "alpha",
        "emission": "emission", "emission_strength": "emission_strength",
    }
    for key, logical in mapping.items():
        if key in params and params[key] is not None:
            version_compat.set_principled_input(bsdf, logical, params[key])


def pbr_generate(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    mat_name = payload.get("material_name", f"PBR_{obj.name}")
    mat = _new_pbr_material(mat_name)
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    _apply_params(bsdf, payload)

    # 可选：贴图通道接入（颜色 / 法线 / 粗糙度 / AO 图片路径）
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    transfer_dir = paths.subdir("transfer")
    for channel, socket_key in (("color_image", "base_color"),
                                ("normal_image", "normal"),
                                ("roughness_image", "roughness"),
                                ("ao_image", "base_color")):
        image_path = payload.get(channel)
        if not image_path:
            continue
        # 贴图仅允许读取传输缓存目录内的文件，防本地任意图片加载
        if not paths.is_within(transfer_dir, os.path.abspath(image_path)):
            ctx.log("warning", f"贴图路径越出传输目录，已忽略: {image_path}")
            continue
        if not os.path.isfile(image_path):
            continue
        try:
            image = bpy.data.images.load(image_path, check_existing=True)
            tex = nodes.new("ShaderNodeTexImage")
            tex.image = image
            socket = version_compat.get_principled_input(bsdf, socket_key)
            if socket is not None:
                links.new(tex.outputs["Color"], socket)
        except (OSError, RuntimeError):
            ctx.log("warning", f"贴图加载失败: {image_path}")

    obj.data.materials.append(mat)
    return {"object": obj.name, "material": mat.name,
            "channels": [k for k in ("base_color", "metallic", "roughness",
                                     "alpha", "emission") if k in payload]}


def batch_replace(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    objects = H.list_objects(payload.get("objects"))
    material_name = payload["material_name"]
    mat = bpy.data.materials.get(material_name)
    if mat is None:
        raise KeyError(f"材质不存在: {material_name}")
    replaced: List[str] = []
    for obj in objects:
        if obj.type != "MESH":
            continue
        obj.data.materials.clear()
        obj.data.materials.append(mat)
        replaced.append(obj.name)
    return {"replaced": replaced, "material": material_name}


def batch_adjust(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    objects = H.list_objects(payload.get("objects"))
    params = payload.get("params", {})
    adjusted: List[str] = []
    for obj in objects:
        if obj.type != "MESH" or not obj.data.materials:
            continue
        for mat in obj.data.materials:
            bsdf = next((n for n in mat.node_tree.nodes
                         if n.type == "BSDF_PRINCIPLED"), None)
            if bsdf is not None:
                _apply_params(bsdf, params)
        adjusted.append(obj.name)
    return {"adjusted": adjusted, "params": list(params.keys())}


def preset_save(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    name = paths.safe_name(payload["name"])
    obj = H.require_object(payload["object"])
    mat = obj.active_material
    if mat is None:
        raise KeyError("当前对象未挂载材质")
    bsdf = next((n for n in mat.node_tree.nodes
                 if n.type == "BSDF_PRINCIPLED"), None)
    preset: Dict[str, Any] = {"name": name, "material": mat.name, "params": {}}
    if bsdf is not None:
        for logical in ("base_color", "metallic", "roughness", "ior", "alpha"):
            sock = version_compat.get_principled_input(bsdf, logical)
            if sock is not None:
                preset["params"][logical] = list(sock.default_value) \
                    if hasattr(sock.default_value, "__iter__") else sock.default_value

    preset_dir = paths.subdir("presets")
    preset_path = os.path.join(preset_dir, f"{name}.json")
    with open(preset_path, "w", encoding="utf-8") as fh:
        json.dump(preset, fh, ensure_ascii=False, indent=2)
    return {"preset": name, "path": preset_path}


def preset_load(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    name = paths.safe_name(payload["name"])
    preset_path = os.path.join(paths.subdir("presets"), f"{name}.json")
    if not os.path.isfile(preset_path):
        raise FileNotFoundError(f"预设不存在: {name}")
    with open(preset_path, "r", encoding="utf-8") as fh:
        preset = json.load(fh)

    obj = H.require_object(payload["object"])
    mat = _new_pbr_material(f"Preset_{name}")
    bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    _apply_params(bsdf, preset.get("params", {}))
    obj.data.materials.append(mat)
    return {"object": obj.name, "material": mat.name, "preset": name}


def duplicate(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """复制源对象当前材质，可挂载到目标对象。"""
    src = H.require_object(payload["object"])
    src_mat = src.active_material
    if src_mat is None:
        raise KeyError("源对象未挂载材质")
    new_mat = src_mat.copy()
    new_mat.name = payload.get("new_name", f"{src_mat.name}_copy")
    target = H.require_object(payload["target"]) if payload.get("target") else src
    target.data.materials.append(new_mat)
    return {"source": src.name, "material": new_mat.name, "target": target.name}


def register(dispatcher) -> None:
    dispatcher.register("material.pbr_generate", pbr_generate, ["object"])
    dispatcher.register("material.batch_replace", batch_replace,
                        ["material_name"])
    dispatcher.register("material.batch_adjust", batch_adjust)
    dispatcher.register("material.preset_save", preset_save, ["name", "object"])
    dispatcher.register("material.preset_load", preset_load, ["name", "object"])
    dispatcher.register("material.duplicate", duplicate, ["object"])
