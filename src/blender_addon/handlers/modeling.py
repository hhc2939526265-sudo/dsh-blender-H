# -*- coding: utf-8 -*-
"""
通用建模指令集（Blender 端）。

覆盖基础几何体、布尔、挤出 / 环切 / 倒角、修改器、拓扑优化、
吸附对齐、原点归位、法线翻转、面数精简、批量参数化生成等 25+ 操作。
所有处理器签名统一为 ``handler(payload, ctx) -> dict``。
"""

from __future__ import annotations

import bpy
import random
from typing import Any, Dict, List

from ..compat import version_compat
from . import _helpers as H

# 基础几何体算子映射
_PRIMITIVE_OPS = {
    "cube": bpy.ops.mesh.primitive_cube_add,
    "sphere": bpy.ops.mesh.primitive_uv_sphere_add,
    "ico_sphere": bpy.ops.mesh.primitive_ico_sphere_add,
    "cylinder": bpy.ops.mesh.primitive_cylinder_add,
    "cone": bpy.ops.mesh.primitive_cone_add,
    "torus": bpy.ops.mesh.primitive_torus_add,
    "plane": bpy.ops.mesh.primitive_plane_add,
    "grid": bpy.ops.mesh.primitive_grid_add,
    "monkey": bpy.ops.mesh.primitive_monkey_add,
}


# ---------------------------------------------------------------------------
# 1. 基础几何体生成
# ---------------------------------------------------------------------------
def add_primitive(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    ptype = payload.get("type", "cube")
    if ptype not in _PRIMITIVE_OPS:
        raise ValueError(f"不支持的几何体类型: {ptype}")

    location = payload.get("location", (0.0, 0.0, 0.0))
    rotation = payload.get("rotation", (0.0, 0.0, 0.0))
    scale = payload.get("scale", (1.0, 1.0, 1.0))
    name = H.unique_name(payload.get("name", ptype))

    op = _PRIMITIVE_OPS[ptype]
    kwargs: Dict[str, Any] = {"location": location, "rotation": rotation}
    # 各算子细分参数按需透传
    for key in ("radius", "depth", "vertices", "ring_count",
                "major_radius", "minor_radius", "subdivisions"):
        if key in payload:
            kwargs[key] = payload[key]
    op(**kwargs)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    if payload.get("smooth", False):
        version_compat.shade_smooth(obj)
    return {"object": obj.name, "type": ptype,
            "vertices": len(obj.data.vertices)}


# ---------------------------------------------------------------------------
# 2. 布尔运算
# ---------------------------------------------------------------------------
def boolean(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    target = H.require_object(payload["target"])
    operand = H.require_object(payload["operand"])
    operation = payload.get("operation", "UNION")  # UNION / DIFFERENCE / INTERSECT
    mod = H.add_modifier(target, "BOOLEAN", f"bool_{operation.lower()}")
    mod.operation = operation
    mod.object = operand
    if payload.get("apply", True):
        version_compat.apply_modifier(target, mod.name)
        bpy.data.objects.remove(operand, do_unlink=True)
    return {"object": target.name, "operation": operation,
            "vertices": len(target.data.vertices)}


# ---------------------------------------------------------------------------
# 3. 挤出
# ---------------------------------------------------------------------------
def extrude(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    amount = float(payload.get("amount", 0.1))
    version_compat.set_active(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.extrude_region_move(TRANSFORM_OT_translate={"value": (0, 0, amount)})
    bpy.ops.object.mode_set(mode="OBJECT")
    return {"object": obj.name, "extrude": amount}


# ---------------------------------------------------------------------------
# 4. 环切
# ---------------------------------------------------------------------------
def loop_cut(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    cuts = int(payload.get("cuts", 1))
    version_compat.set_active(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.loopcut_slide(
        MESH_OT_loopcut={"number_cuts": cuts, "smoothness": 0,
                         "falloff": "SMOOTH", "use_even_offset": True})
    bpy.ops.object.mode_set(mode="OBJECT")
    return {"object": obj.name, "cuts": cuts}


# ---------------------------------------------------------------------------
# 5. 倒角
# ---------------------------------------------------------------------------
def bevel(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    mod = H.add_modifier(obj, "BEVEL", "bevel")
    mod.width = float(payload.get("width", 0.05))
    mod.segments = int(payload.get("segments", 3))
    if payload.get("apply", False):
        version_compat.apply_modifier(obj, mod.name)
    return {"object": obj.name, "width": mod.width, "segments": mod.segments}


# ---------------------------------------------------------------------------
# 6. 阵列修改器
# ---------------------------------------------------------------------------
def array(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    mod = H.add_modifier(obj, "ARRAY", "array")
    mod.count = int(payload.get("count", 3))
    offset = payload.get("relative_offset", (1.0, 0.0, 0.0))
    mod.use_relative_offset = True
    mod.relative_offset_displace = offset
    if payload.get("apply", False):
        version_compat.apply_modifier(obj, mod.name)
    return {"object": obj.name, "count": mod.count}


# ---------------------------------------------------------------------------
# 7. 曲线生成
# ---------------------------------------------------------------------------
def curve(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    points: List[List[float]] = payload.get("points") or []
    if len(points) < 2:
        raise ValueError("曲线至少需要 2 个坐标点")
    for co in points:
        if not isinstance(co, (list, tuple)) or len(co) < 3:
            raise ValueError("曲线坐标点至少包含 X / Y / Z 三个分量")
    name = H.unique_name(payload.get("name", "curve"))
    curve_data = bpy.data.curves.new(name=name, type="CURVE")
    curve_data.dimensions = "3D"
    curve_data.resolution_u = 2
    curve_data.bevel_depth = float(payload.get("bevel_depth", 0.02))
    spline = curve_data.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for pt, co in zip(spline.points, points):
        pt.co = (co[0], co[1], co[2], 1.0)
    spline.use_cyclic_u = payload.get("cyclic", False)
    obj = bpy.data.objects.new(name, curve_data)
    bpy.context.collection.objects.link(obj)
    return {"object": obj.name, "points": len(points)}


# ---------------------------------------------------------------------------
# 8. 实体化
# ---------------------------------------------------------------------------
def solidify(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    mod = H.add_modifier(obj, "SOLIDIFY", "solidify")
    mod.thickness = float(payload.get("thickness", 0.02))
    if payload.get("apply", False):
        version_compat.apply_modifier(obj, mod.name)
    return {"object": obj.name, "thickness": mod.thickness}


# ---------------------------------------------------------------------------
# 9. 重网格化
# ---------------------------------------------------------------------------
def remesh(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    mod = H.add_modifier(obj, "REMESH", "remesh")
    mod.mode = "VOXEL"
    mod.voxel_size = float(payload.get("voxel_size", 0.05))
    if payload.get("apply", True):
        version_compat.apply_modifier(obj, mod.name)
    return {"object": obj.name, "vertices": len(obj.data.vertices)}


# ---------------------------------------------------------------------------
# 10. 内插面
# ---------------------------------------------------------------------------
def inset(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    version_compat.set_active(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.inset(thickness=float(payload.get("thickness", 0.05)),
                       depth=float(payload.get("depth", 0.0)))
    bpy.ops.object.mode_set(mode="OBJECT")
    return {"object": obj.name}


# ---------------------------------------------------------------------------
# 11. 细分
# ---------------------------------------------------------------------------
def subdivide(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    mod = H.add_modifier(obj, "SUBSURF", "subsurf")
    mod.levels = int(payload.get("levels", 1))
    mod.render_levels = int(payload.get("render_levels", mod.levels))
    if payload.get("apply", False):
        version_compat.apply_modifier(obj, mod.name)
    return {"object": obj.name, "levels": mod.levels}


# ---------------------------------------------------------------------------
# 12. 面数精简
# ---------------------------------------------------------------------------
def decimate(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    mod = H.add_modifier(obj, "DECIMATE", "decimate")
    mod.ratio = float(payload.get("ratio", 0.5))
    if payload.get("apply", True):
        version_compat.apply_modifier(obj, mod.name)
    return {"object": obj.name, "vertices": len(obj.data.vertices)}


# ---------------------------------------------------------------------------
# 13. 法线统一
# ---------------------------------------------------------------------------
def recalc_normals(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    version_compat.set_active(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    return {"object": obj.name}


# ---------------------------------------------------------------------------
# 14. 原点归位
# ---------------------------------------------------------------------------
def origin_set(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    target = payload.get("target", "ORIGIN_GEOMETRY")  # ORIGIN_GEOMETRY / ORIGIN_CURSOR
    version_compat.set_active(obj)
    bpy.ops.object.origin_set(type=target)
    return {"object": obj.name, "origin": list(obj.location)}


# ---------------------------------------------------------------------------
# 15. 吸附对齐
# ---------------------------------------------------------------------------
def align(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    target = H.require_object(payload["target"])
    axis = payload.get("axis", "XYZ")
    for i, axis_name in enumerate(("X", "Y", "Z")):
        if axis_name in axis:
            obj.location[i] = target.location[i]
    return {"object": obj.name, "target": target.name, "axis": axis}


# ---------------------------------------------------------------------------
# 16. 法线翻转
# ---------------------------------------------------------------------------
def flip_normals(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    version_compat.set_active(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.flip_normals()
    bpy.ops.object.mode_set(mode="OBJECT")
    return {"object": obj.name}


# ---------------------------------------------------------------------------
# 17. 重命名
# ---------------------------------------------------------------------------
def rename(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    new_name = H.unique_name(payload["new_name"])
    obj.name = new_name
    if obj.type == "MESH":
        obj.data.name = new_name
    return {"object": new_name}


# ---------------------------------------------------------------------------
# 18. 参数化批量生成
# ---------------------------------------------------------------------------
def batch_generate(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    count = int(payload.get("count", 5))
    ptype = payload.get("type", "cube")
    prefix = payload.get("name_prefix", "batch")
    loc_range = payload.get("location_range", [[-2, 2], [-2, 2], [0, 2]])
    scale_range = payload.get("scale_range", [[0.5, 1.0], [0.5, 1.0], [0.5, 1.0]])
    rng = random.Random(payload.get("seed", 42))

    created: List[str] = []
    for i in range(count):
        loc = [rng.uniform(*rng_) for rng_ in loc_range]
        scl = [rng.uniform(*rng_) for rng_ in scale_range]
        res = add_primitive({"type": ptype, "location": loc, "scale": scl,
                             "name": f"{prefix}_{i:03d}"}, ctx)
        created.append(res["object"])
    return {"created": created, "count": len(created)}


# ---------------------------------------------------------------------------
# 19. 删除对象
# ---------------------------------------------------------------------------
def delete(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    objs = H.list_objects(payload.get("objects"))
    names = [o.name for o in objs]
    for obj in objs:
        bpy.data.objects.remove(obj, do_unlink=True)
    return {"deleted": names}


# ---------------------------------------------------------------------------
# 20. 选择
# ---------------------------------------------------------------------------
def select(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    H.deselect_all()
    if payload.get("mode") == "ALL":
        bpy.ops.object.select_all(action="SELECT")
        return {"selected": [o.name for o in bpy.context.selected_objects]}
    objs = H.list_objects(payload.get("objects"))
    for obj in objs:
        obj.select_set(True)
    if objs:
        bpy.context.view_layer.objects.active = objs[0]
    return {"selected": [o.name for o in objs]}


# ---------------------------------------------------------------------------
# 21. 镜像修改器
# ---------------------------------------------------------------------------
def mirror(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    mod = H.add_modifier(obj, "MIRROR", "mirror")
    axis = payload.get("axis", "X")
    mod.use_x = axis == "X"
    mod.use_y = axis == "Y"
    mod.use_z = axis == "Z"
    mod.use_clip = payload.get("clip", True)
    if payload.get("apply", False):
        version_compat.apply_modifier(obj, mod.name)
    return {"object": obj.name, "axis": axis}


# ---------------------------------------------------------------------------
# 22. 焊接（按距离合并顶点）
# ---------------------------------------------------------------------------
def weld(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    version_compat.set_active(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=float(payload.get("distance", 0.0001)))
    bpy.ops.object.mode_set(mode="OBJECT")
    return {"object": obj.name, "vertices": len(obj.data.vertices)}


# ---------------------------------------------------------------------------
# 23. 平滑着色
# ---------------------------------------------------------------------------
def smooth(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    version_compat.shade_smooth(obj)
    return {"object": obj.name}


# ---------------------------------------------------------------------------
# 24. UV 自动展开
# ---------------------------------------------------------------------------
def uv_unwrap(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    version_compat.set_active(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=float(payload.get("angle_limit", 66.0)))
    bpy.ops.object.mode_set(mode="OBJECT")
    return {"object": obj.name, "uv_layers": len(obj.data.uv_layers)}


# ---------------------------------------------------------------------------
# 25. 应用全部修改器
# ---------------------------------------------------------------------------
def apply_all(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    applied: List[str] = []
    for mod in list(obj.modifiers):
        if version_compat.apply_modifier(obj, mod.name):
            applied.append(mod.name)
    return {"object": obj.name, "applied": applied}


# ---------------------------------------------------------------------------
# 26. 变换（位移 / 旋转 / 缩放）
# ---------------------------------------------------------------------------
def transform(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    H.set_transform(obj, payload)
    if payload.get("apply", False):
        H.apply_transform(obj)
    return {"object": obj.name, "location": list(obj.location),
            "rotation": list(obj.rotation_euler), "scale": list(obj.scale)}


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------
def register(dispatcher) -> None:
    """将本模块全部处理器挂载到分发器。"""
    dispatcher.register("mesh.add_primitive", add_primitive, ["type"])
    dispatcher.register("mesh.boolean", boolean, ["target", "operand"])
    dispatcher.register("mesh.extrude", extrude, ["object"])
    dispatcher.register("mesh.loop_cut", loop_cut, ["object"])
    dispatcher.register("mesh.bevel", bevel, ["object"])
    dispatcher.register("mesh.array", array, ["object"])
    dispatcher.register("mesh.curve", curve, ["points"])
    dispatcher.register("mesh.solidify", solidify, ["object"])
    dispatcher.register("mesh.remesh", remesh, ["object"])
    dispatcher.register("mesh.inset", inset, ["object"])
    dispatcher.register("mesh.subdivide", subdivide, ["object"])
    dispatcher.register("mesh.decimate", decimate, ["object"])
    dispatcher.register("mesh.recalc_normals", recalc_normals, ["object"])
    dispatcher.register("mesh.origin_set", origin_set, ["object"])
    dispatcher.register("mesh.align", align, ["object", "target"])
    dispatcher.register("mesh.flip_normals", flip_normals, ["object"])
    dispatcher.register("mesh.rename", rename, ["object", "new_name"])
    dispatcher.register("mesh.batch_generate", batch_generate, ["count", "type"])
    dispatcher.register("mesh.delete", delete)
    dispatcher.register("mesh.select", select)
    dispatcher.register("mesh.mirror", mirror, ["object"])
    dispatcher.register("mesh.weld", weld, ["object"])
    dispatcher.register("mesh.smooth", smooth, ["object"])
    dispatcher.register("mesh.uv_unwrap", uv_unwrap, ["object"])
    dispatcher.register("mesh.apply_all", apply_all, ["object"])
    dispatcher.register("mesh.transform", transform, ["object"])
