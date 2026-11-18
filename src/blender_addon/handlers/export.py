# -*- coding: utf-8 -*-
"""
反向链路：Blender 资产 / 动画 / 材质 / 场景一键回传 DSH。

- 网格资产 → glTF(.glb) 导出后分片回传
- 动画 → 骨骼关键帧轨迹 JSON + 关联网格 glb
- 材质 → 参数 JSON 直接回执（小数据走协议体，不走文件分片）
- 场景 → 全场景 glb 导出回传

回传结果可在 DSH 端再次进入 AI 优化链路，形成多轮迭代闭环。
"""

from __future__ import annotations

import os
import json
import time
import bpy
from typing import Any, Dict, List, Optional

from ..utils import paths
from . import _helpers as H


def _export_glb(objects: Optional[List[bpy.types.Object]], filepath: str,
                ctx) -> str:
    """导出 glb；objects 为空时导出全场景。"""
    if objects:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in objects:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = objects[0]
        use_selection = True
    else:
        use_selection = False
    bpy.ops.export_scene.gltf(
        filepath=filepath, export_format="GLB",
        use_selection=use_selection, export_animations=True)
    return filepath


def export_asset(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    objects = H.list_objects(payload.get("objects"))
    stamp = time.strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(paths.subdir("temp"), f"asset_{stamp}.glb")
    _export_glb(objects or None, filepath, ctx)
    back = ctx.bridge.send_file_back(ctx.bridge.current_conn_id, filepath,
                                     {"kind": "asset_glb"})
    return {"asset": filepath, "objects": [o.name for o in (objects or [])],
            "file_back": back}


def export_animation(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    armature = H.require_object(payload["object"])
    action = armature.animation_data.action if armature.animation_data else None
    trajectory: Dict[str, Any] = {"armature": armature.name, "fps":
                                  bpy.context.scene.render.fps, "bones": {}}
    if action is not None:
        for fcurve in action.fcurves:
            bone = fcurve.group.name if fcurve.group else fcurve.data_path
            trajectory["bones"].setdefault(bone, {"fcurves": []})
            trajectory["bones"][bone]["fcurves"].append({
                "data_path": fcurve.data_path,
                "array_index": fcurve.array_index,
                "points": [[round(k.co[0], 3), round(k.co[1], 5)]
                           for k in fcurve.keyframe_points],
            })

    # 关联网格一并导出 glb
    stamp = time.strftime("%Y%m%d_%H%M%S")
    glb_path = os.path.join(paths.subdir("temp"), f"anim_{stamp}.glb")
    _export_glb([armature], glb_path, ctx)
    glb_back = ctx.bridge.send_file_back(ctx.bridge.current_conn_id, glb_path,
                                         {"kind": "animation_glb"})

    # 轨迹 JSON 走协议体直接回传
    json_path = os.path.join(paths.subdir("temp"), f"anim_{stamp}.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(trajectory, fh, ensure_ascii=False, indent=2)
    json_back = ctx.bridge.send_file_back(ctx.bridge.current_conn_id, json_path,
                                          {"kind": "animation_json"})
    return {"trajectory": trajectory, "glb": glb_back, "json": json_back}


def export_material(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    objects = H.list_objects(payload.get("objects"))
    materials: List[Dict[str, Any]] = []
    for obj in objects:
        if obj.type != "MESH":
            continue
        for mat in obj.data.materials:
            materials.append({
                "object": obj.name, "material": mat.name,
                "use_nodes": mat.use_nodes,
                "diffuse_color": list(mat.diffuse_color),
            })
    return {"materials": materials, "count": len(materials)}


def export_scene(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    filepath = os.path.join(paths.subdir("temp"), f"scene_{stamp}.glb")
    _export_glb(None, filepath, ctx)
    back = ctx.bridge.send_file_back(ctx.bridge.current_conn_id, filepath,
                                     {"kind": "scene_glb"})
    return {"scene": filepath, "object_count": len(bpy.data.objects),
            "file_back": back}


def register(dispatcher) -> None:
    dispatcher.register("export.asset", export_asset)
    dispatcher.register("export.animation", export_animation, ["object"])
    dispatcher.register("export.material", export_material)
    dispatcher.register("export.scene", export_scene)
