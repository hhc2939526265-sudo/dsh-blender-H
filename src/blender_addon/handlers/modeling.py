# -*- coding: utf-8 -*-
"""
通用建模指令集（Blender 端）。

覆盖基础几何体、布尔、挤出 / 环切 / 倒角、修改器、拓扑优化、
吸附对齐、原点归位、法线翻转、面数精简、批量参数化生成等 25+ 操作。
所有处理器签名统一为 ``handler(payload, ctx) -> dict``。
"""

from __future__ import annotations

import math
import bpy
import random
from typing import Any, Dict, List

from ..compat import version_compat
from ..utils.errors import (ParamError, as_int, get_bool, get_float, get_int,
                            get_list, get_str, get_vec3, require_float_list,
                            require_list, require_vec3)
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


def _require_range(value: Any, param: str) -> List[Any]:
    """校验 [[最小, 最大], ...] 形式的数值区间列表。"""
    items = require_list(value, param, min_len=1)
    ranges: List[Any] = []
    for index, item in enumerate(items):
        pair = require_float_list(item, f"{param}[{index}]", min_len=2)
        if len(pair) != 2:
            raise ParamError(
                f"{param}[{index}] 需为 [最小值, 最大值] 两个数字")
        ranges.append((pair[0], pair[1]))
    return ranges


# ---------------------------------------------------------------------------
# 1. 基础几何体生成
# ---------------------------------------------------------------------------
def add_primitive(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    ptype = get_str(payload, "type", "cube")
    if ptype not in _PRIMITIVE_OPS:
        raise ParamError(f"不支持的几何体类型: {ptype}")

    location = get_vec3(payload, "location", (0.0, 0.0, 0.0))
    rotation = get_vec3(payload, "rotation", (0.0, 0.0, 0.0))
    scale = get_vec3(payload, "scale", (1.0, 1.0, 1.0))
    name = H.unique_name(payload.get("name", ptype), "name")

    op = _PRIMITIVE_OPS[ptype]
    kwargs: Dict[str, Any] = {"location": location, "rotation": rotation}
    # 各算子细分参数按需透传（数字参数先做类型校验，避免 C API 晦涩报错）
    for key in ("radius", "depth", "major_radius", "minor_radius"):
        if key in payload:
            kwargs[key] = get_float(payload, key)
    for key in ("vertices", "ring_count", "subdivisions"):
        if key in payload:
            kwargs[key] = get_int(payload, key)
    op(**kwargs)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    if get_bool(payload, "smooth", False):
        version_compat.shade_smooth(obj)
    return {"object": obj.name, "type": ptype,
            "vertices": len(obj.data.vertices)}


# ---------------------------------------------------------------------------
# 2. 布尔运算
# ---------------------------------------------------------------------------
def boolean(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    target = H.require_mesh(H.require_object(payload["target"]), "布尔运算目标")
    operand = H.require_mesh(H.require_object(payload["operand"]), "布尔运算操作体")
    operation = get_str(payload, "operation", "UNION")  # UNION / DIFFERENCE / INTERSECT
    if operation not in ("UNION", "DIFFERENCE", "INTERSECT"):
        raise ParamError(
            f"布尔运算类型非法: {operation}（UNION / DIFFERENCE / INTERSECT）")
    mod = H.add_modifier(target, "BOOLEAN", f"bool_{operation.lower()}")
    mod.operation = operation
    mod.object = operand
    if get_bool(payload, "apply", True):
        version_compat.apply_modifier(target, mod.name)
        bpy.data.objects.remove(operand, do_unlink=True)
    return {"object": target.name, "operation": operation,
            "vertices": len(target.data.vertices)}


# ---------------------------------------------------------------------------
# 3. 挤出
# ---------------------------------------------------------------------------
def extrude(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_mesh(H.require_object(payload["object"]), "挤出")
    amount = get_float(payload, "amount", 0.1)
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
    obj = H.require_mesh(H.require_object(payload["object"]), "环切")
    cuts = get_int(payload, "cuts", 1)
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
    mod.width = get_float(payload, "width", 0.05)
    mod.segments = get_int(payload, "segments", 3)
    if get_bool(payload, "apply", False):
        version_compat.apply_modifier(obj, mod.name)
    return {"object": obj.name, "width": mod.width, "segments": mod.segments}


# ---------------------------------------------------------------------------
# 6. 阵列修改器
# ---------------------------------------------------------------------------
def array(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    mod = H.add_modifier(obj, "ARRAY", "array")
    mod.count = get_int(payload, "count", 3)
    offset = get_vec3(payload, "relative_offset", (1.0, 0.0, 0.0))
    mod.use_relative_offset = True
    mod.relative_offset_displace = offset
    if get_bool(payload, "apply", False):
        version_compat.apply_modifier(obj, mod.name)
    return {"object": obj.name, "count": mod.count}


# ---------------------------------------------------------------------------
# 7. 曲线生成
# ---------------------------------------------------------------------------
def curve(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    points = get_list(payload, "points")
    if len(points) < 2:
        raise ParamError("曲线至少需要 2 个坐标点")
    points = [require_float_list(co, f"points[{index}]", min_len=3)
              for index, co in enumerate(points)]
    name = H.unique_name(get_str(payload, "name", "curve"), "name")
    curve_data = bpy.data.curves.new(name=name, type="CURVE")
    curve_data.dimensions = "3D"
    curve_data.resolution_u = 2
    curve_data.bevel_depth = get_float(payload, "bevel_depth", 0.02)
    spline = curve_data.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for pt, co in zip(spline.points, points):
        pt.co = (co[0], co[1], co[2], 1.0)
    spline.use_cyclic_u = get_bool(payload, "cyclic", False)
    obj = bpy.data.objects.new(name, curve_data)
    bpy.context.collection.objects.link(obj)
    return {"object": obj.name, "points": len(points)}


# ---------------------------------------------------------------------------
# 8. 实体化
# ---------------------------------------------------------------------------
def solidify(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    mod = H.add_modifier(obj, "SOLIDIFY", "solidify")
    mod.thickness = get_float(payload, "thickness", 0.02)
    if get_bool(payload, "apply", False):
        version_compat.apply_modifier(obj, mod.name)
    return {"object": obj.name, "thickness": mod.thickness}


# ---------------------------------------------------------------------------
# 9. 重网格化
# ---------------------------------------------------------------------------
def remesh(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    mod = H.add_modifier(obj, "REMESH", "remesh")
    mod.mode = "VOXEL"
    mod.voxel_size = get_float(payload, "voxel_size", 0.05)
    if get_bool(payload, "apply", True):
        version_compat.apply_modifier(obj, mod.name)
    return {"object": obj.name, "vertices": len(obj.data.vertices)}


# ---------------------------------------------------------------------------
# 10. 内插面
# ---------------------------------------------------------------------------
def inset(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_mesh(H.require_object(payload["object"]), "内插面")
    version_compat.set_active(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.inset(thickness=get_float(payload, "thickness", 0.05),
                       depth=get_float(payload, "depth", 0.0))
    bpy.ops.object.mode_set(mode="OBJECT")
    return {"object": obj.name}


# ---------------------------------------------------------------------------
# 11. 细分
# ---------------------------------------------------------------------------
def subdivide(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    mod = H.add_modifier(obj, "SUBSURF", "subsurf")
    mod.levels = get_int(payload, "levels", 1)
    mod.render_levels = get_int(payload, "render_levels", mod.levels)
    if get_bool(payload, "apply", False):
        version_compat.apply_modifier(obj, mod.name)
    return {"object": obj.name, "levels": mod.levels}


# ---------------------------------------------------------------------------
# 12. 面数精简
# ---------------------------------------------------------------------------
def decimate(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    mod = H.add_modifier(obj, "DECIMATE", "decimate")
    mod.ratio = get_float(payload, "ratio", 0.5)
    if get_bool(payload, "apply", True):
        version_compat.apply_modifier(obj, mod.name)
    return {"object": obj.name, "vertices": len(obj.data.vertices)}


# ---------------------------------------------------------------------------
# 13. 法线统一
# ---------------------------------------------------------------------------
def recalc_normals(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_mesh(H.require_object(payload["object"]), "法线统一")
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
    target = get_str(payload, "target", "ORIGIN_GEOMETRY")  # ORIGIN_GEOMETRY / ORIGIN_CURSOR
    version_compat.set_active(obj)
    bpy.ops.object.origin_set(type=target)
    return {"object": obj.name, "origin": list(obj.location)}


# ---------------------------------------------------------------------------
# 15. 吸附对齐
# ---------------------------------------------------------------------------
def align(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    target = H.require_object(payload["target"])
    axis = get_str(payload, "axis", "XYZ")
    for i, axis_name in enumerate(("X", "Y", "Z")):
        if axis_name in axis:
            obj.location[i] = target.location[i]
    return {"object": obj.name, "target": target.name, "axis": axis}


# ---------------------------------------------------------------------------
# 16. 法线翻转
# ---------------------------------------------------------------------------
def flip_normals(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_mesh(H.require_object(payload["object"]), "法线翻转")
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
    new_name = H.unique_name(payload["new_name"], "new_name")
    obj.name = new_name
    if obj.type == "MESH":
        obj.data.name = new_name
    return {"object": new_name}


# ---------------------------------------------------------------------------
# 18. 参数化批量生成
# ---------------------------------------------------------------------------
def batch_generate(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    count = get_int(payload, "count", 5)
    ptype = get_str(payload, "type", "cube")
    prefix = get_str(payload, "name_prefix", "batch")
    loc_range = _require_range(
        payload.get("location_range", [[-2, 2], [-2, 2], [0, 2]]),
        "location_range")
    scale_range = _require_range(
        payload.get("scale_range", [[0.5, 1.0], [0.5, 1.0], [0.5, 1.0]]),
        "scale_range")
    seed = payload.get("seed", 42)
    rng = random.Random(42 if seed is None else as_int(seed, "seed"))

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
    axis = get_str(payload, "axis", "X")
    mod.use_x = axis == "X"
    mod.use_y = axis == "Y"
    mod.use_z = axis == "Z"
    mod.use_clip = get_bool(payload, "clip", True)
    if get_bool(payload, "apply", False):
        version_compat.apply_modifier(obj, mod.name)
    return {"object": obj.name, "axis": axis}


# ---------------------------------------------------------------------------
# 22. 焊接（按距离合并顶点）
# ---------------------------------------------------------------------------
def weld(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_mesh(H.require_object(payload["object"]), "焊接顶点")
    version_compat.set_active(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=get_float(payload, "distance", 0.0001))
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
    obj = H.require_mesh(H.require_object(payload["object"]), "UV 展开")
    version_compat.set_active(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.uv.smart_project(angle_limit=get_float(payload, "angle_limit", 66.0))
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
    if get_bool(payload, "apply", False):
        H.apply_transform(obj)
    return {"object": obj.name, "location": list(obj.location),
            "rotation": list(obj.rotation_euler), "scale": list(obj.scale)}


# ---------------------------------------------------------------------------
# 27. 复制对象（角色 / 道具复用）
# ---------------------------------------------------------------------------
def duplicate(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    linked = get_bool(payload, "linked", False)
    new_obj = obj.copy()
    if not linked:
        new_obj.data = obj.data.copy()
    bpy.context.collection.objects.link(new_obj)
    new_obj.name = H.unique_name(
        get_str(payload, "name", f"{obj.name}_dup"), "name")
    H.set_transform(new_obj, payload)
    return {"source": obj.name, "object": new_obj.name, "linked": linked}


# ---------------------------------------------------------------------------
# 28. 合并多对象到目标（角色部件 / 场景道具整合）
# ---------------------------------------------------------------------------
def join(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    target = H.require_mesh(H.require_object(payload["object"]), "合并到目标")
    # 二次复核成员：剔除已失效句柄与非网格对象（曲线 / 骨架 / 灯光 / 相机），
    # 避免触碰失效 RNA 或在非网格对象上触发构造性算子错误。
    members: List[bpy.types.Object] = []
    skipped: List[Dict[str, Any]] = []
    for m in H.list_objects(payload.get("objects")):
        if m == target:
            continue
        if not H.is_object_alive(m):
            skipped.append({"name": getattr(m, "name", "<失效>"),
                            "reason": "对象引用已失效"})
            continue
        if m.type != "MESH":
            skipped.append({"name": m.name, "type": m.type,
                            "reason": "非网格对象，已跳过（可先调用 mesh.convert）"})
            continue
        members.append(m)
    H.deselect_all()
    version_compat.set_active(target)
    for m in members:
        m.select_set(True)
    bpy.ops.object.join()
    return {"object": target.name,
            "joined": [m.name for m in members], "skipped": skipped}


# ---------------------------------------------------------------------------
# 28b. 曲线 / 文字 / 元球转网格（网格类操作前置步骤）
# ---------------------------------------------------------------------------
def convert(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    """将 CURVE / FONT / META / SURFACE 对象转换为网格对象。"""
    obj = H.require_object(payload["object"])
    if obj.type == "MESH":
        return {"object": obj.name, "converted": False, "type": "MESH"}
    if obj.type not in ("CURVE", "FONT", "META", "SURFACE"):
        raise ParamError(f"类型 {obj.type} 不支持转换为网格")
    H.deselect_all()
    obj.select_set(True)
    version_compat.set_active(obj)
    bpy.ops.object.convert(target="MESH")
    new_obj = bpy.context.active_object
    return {"object": new_obj.name, "converted": True, "type": new_obj.type}


# ---------------------------------------------------------------------------
# 29. 按松散块分离
# ---------------------------------------------------------------------------
def separate(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_mesh(H.require_object(payload["object"]), "分离")
    sep_type = get_str(payload, "type", "LOOSE")
    if sep_type not in ("LOOSE", "MATERIAL", "SELECTION"):
        raise ParamError(f"分离类型非法: {sep_type}（LOOSE / MATERIAL / SELECTION）")
    version_compat.set_active(obj)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.separate(type=sep_type)
    bpy.ops.object.mode_set(mode="OBJECT")
    return {"object": obj.name, "type": sep_type}


# ---------------------------------------------------------------------------
# 30. 螺旋修改器（螺纹 / 卷曲线条 / 角色装饰）
# ---------------------------------------------------------------------------
def screw(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    mod = H.add_modifier(obj, "SCREW", "screw")
    mod.angle = get_float(payload, "angle", 2 * math.pi)
    mod.steps = get_int(payload, "steps", 16)
    mod.iterations = get_int(payload, "iterations", 1)
    if get_bool(payload, "apply", False):
        version_compat.apply_modifier(obj, mod.name)
    return {"object": obj.name, "angle": mod.angle, "steps": mod.steps}


# ---------------------------------------------------------------------------
# 31. 线框修改器（骨架 / 网格外壳效果）
# ---------------------------------------------------------------------------
def wireframe(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    mod = H.add_modifier(obj, "WIREFRAME", "wireframe")
    mod.thickness = get_float(payload, "thickness", 0.02)
    mod.offset = get_float(payload, "offset", 0.0)
    mod.use_replace = get_bool(payload, "replace", True)
    if get_bool(payload, "apply", False):
        version_compat.apply_modifier(obj, mod.name)
    return {"object": obj.name, "thickness": mod.thickness}


# ---------------------------------------------------------------------------
# 32. 置换修改器（地形起伏 / 角色表面起伏）
# ---------------------------------------------------------------------------
def displace(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    mod = H.add_modifier(obj, "DISPLACE", "displace")
    mod.strength = get_float(payload, "strength", 0.2)
    mod.mid_level = get_float(payload, "mid_level", 0.5)
    direction = get_str(payload, "direction", "NORMAL")
    if direction in ("NORMAL", "X", "Y", "Z"):
        mod.direction = direction
    if get_bool(payload, "apply", False):
        version_compat.apply_modifier(obj, mod.name)
    return {"object": obj.name, "strength": mod.strength}


# ---------------------------------------------------------------------------
# 33. 锐边拆分修改器
# ---------------------------------------------------------------------------
def edge_split(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    mod = H.add_modifier(obj, "EDGE_SPLIT", "edge_split")
    mod.split_angle = get_float(payload, "split_angle", 30.0)
    if get_bool(payload, "apply", False):
        version_compat.apply_modifier(obj, mod.name)
    return {"object": obj.name, "split_angle": mod.split_angle}


# ---------------------------------------------------------------------------
# 34. 收缩包裹（角色 / 道具贴合目标表面）
# ---------------------------------------------------------------------------
def shrinkwrap(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    target = H.require_object(payload["target"])
    mod = H.add_modifier(obj, "SHRINKWRAP", "shrinkwrap")
    mod.target = target
    method = get_str(payload, "wrap_method", "NEAREST_SURFACEPOINT")
    if method in ("NEAREST_SURFACEPOINT", "PROJECT", "TARGET_PROJECT"):
        mod.wrap_method = method
    mod.offset = get_float(payload, "offset", 0.0)
    if get_bool(payload, "apply", False):
        version_compat.apply_modifier(obj, mod.name)
    return {"object": obj.name, "target": target.name, "method": mod.wrap_method}


# ---------------------------------------------------------------------------
# 35. 边折痕标记（细分时保留硬边）
# ---------------------------------------------------------------------------
def crease(payload: Dict[str, Any], ctx) -> Dict[str, Any]:
    obj = H.require_object(payload["object"])
    if obj.type != "MESH":
        raise ParamError("折痕标记仅支持网格对象")
    value = get_float(payload, "value", 1.0)
    edge_indexes = payload.get("edges")
    if edge_indexes is not None:
        edge_indexes = require_list(edge_indexes, "edges")
    edges = obj.data.edges
    if edge_indexes is None:
        for edge in edges:
            edge.crease = value
    else:
        for index, idx in enumerate(edge_indexes):
            edge_index = as_int(idx, f"edges[{index}]")
            if 0 <= edge_index < len(edges):
                edges[edge_index].crease = value
    return {"object": obj.name, "value": value,
            "edges": len(edges) if edge_indexes is None else len(edge_indexes)}


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
    dispatcher.register("mesh.duplicate", duplicate, ["object"])
    dispatcher.register("mesh.join", join, ["object"])
    dispatcher.register("mesh.convert", convert, ["object"])
    dispatcher.register("mesh.separate", separate, ["object"])
    dispatcher.register("mesh.screw", screw, ["object"])
    dispatcher.register("mesh.wireframe", wireframe, ["object"])
    dispatcher.register("mesh.displace", displace, ["object"])
    dispatcher.register("mesh.edge_split", edge_split, ["object"])
    dispatcher.register("mesh.shrinkwrap", shrinkwrap, ["object", "target"])
    dispatcher.register("mesh.crease", crease, ["object"])
