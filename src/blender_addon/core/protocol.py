# -*- coding: utf-8 -*-
"""
标准化 JSON 通信协议（Blender 端）。

消息信封固定 6 个字段：
    - cmd_id      指令唯一 ID（UUID 字符串）
    - cmd_type    指令类型（见 CommandType 注册表）
    - payload     参数体（dict）
    - status      执行状态：PENDING / RUNNING / SUCCESS / FAILED / CANCELED
    - result      返回结果（dict）
    - error       错误信息（dict：code / message / detail）

本模块只负责信封构造、校验与类型常量定义，不做网络收发。
"""

from __future__ import annotations

import uuid
import time
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# 状态常量
# ---------------------------------------------------------------------------
STATUS_PENDING = "PENDING"
STATUS_RUNNING = "RUNNING"
STATUS_SUCCESS = "SUCCESS"
STATUS_FAILED = "FAILED"
STATUS_CANCELED = "CANCELED"

ALL_STATUS = {STATUS_PENDING, STATUS_RUNNING, STATUS_SUCCESS,
              STATUS_FAILED, STATUS_CANCELED}

# ---------------------------------------------------------------------------
# 指令类型注册表（业务处理器按此派发）
# ---------------------------------------------------------------------------
class CommandType:
    # 连接 / 心跳
    HANDSHAKE = "system.handshake"
    HEARTBEAT = "system.heartbeat"
    PING = "system.ping"
    PONG = "system.pong"
    SHUTDOWN = "system.shutdown"
    SYSTEM_STOP = "system.stop"

    # 文件分片传输
    TRANSFER_BEGIN = "transfer.begin"
    TRANSFER_CHUNK = "transfer.chunk"
    TRANSFER_END = "transfer.end"
    TRANSFER_ACK = "transfer.ack"

    # 建模（通用建模指令集，25+）
    MESH_ADD_PRIMITIVE = "mesh.add_primitive"
    MESH_BOOLEAN = "mesh.boolean"
    MESH_EXTRUDE = "mesh.extrude"
    MESH_LOOP_CUT = "mesh.loop_cut"
    MESH_BEVEL = "mesh.bevel"
    MESH_ARRAY = "mesh.array"
    MESH_CURVE = "mesh.curve"
    MESH_SOLIDIFY = "mesh.solidify"
    MESH_REMESH = "mesh.remesh"
    MESH_INSET = "mesh.inset"
    MESH_SUBDIVIDE = "mesh.subdivide"
    MESH_DECIMATE = "mesh.decimate"
    MESH_RECALC_NORMALS = "mesh.recalc_normals"
    MESH_ORIGIN_SET = "mesh.origin_set"
    MESH_ALIGN = "mesh.align"
    MESH_FLIP_NORMALS = "mesh.flip_normals"
    MESH_NAMING = "mesh.rename"
    MESH_BATCH_GENERATE = "mesh.batch_generate"
    MESH_DELETE = "mesh.delete"
    MESH_SELECT = "mesh.select"
    MESH_MIRROR = "mesh.mirror"
    MESH_WELD = "mesh.weld"
    MESH_SMOOTH = "mesh.smooth"
    MESH_UV_UNWRAP = "mesh.uv_unwrap"
    MESH_APPLY_ALL = "mesh.apply_all"
    MESH_TRANSFORM = "mesh.transform"

    # 角色建模（图片驱动）
    CHARACTER_BUILD = "character.build"
    CHARACTER_RIG = "character.rig"
    CHARACTER_SHAPE_KEYS = "character.shape_keys"
    CHARACTER_UV_BAKE = "character.uv_bake"

    # 动画
    ANIM_KEYFRAME = "anim.keyframe"
    ANIM_RIG_AUTO = "anim.rig_auto"
    ANIM_LOOP_CYCLE = "anim.loop_cycle"
    ANIM_PHYSICS = "anim.physics"
    ANIM_PATH_CONSTRAINT = "anim.path_constraint"
    ANIM_MOCAP_APPLY = "anim.mocap_apply"
    ANIM_TIMING = "anim.timing"
    ANIM_EASING = "anim.easing"

    # 特效
    EFFECT_PARTICLE = "effect.particle"
    EFFECT_GLOW = "effect.glow"
    EFFECT_FLUID = "effect.fluid"
    EFFECT_DEFORM = "effect.deform"
    EFFECT_CAMERA_MATCH = "effect.camera_match"

    # 材质
    MAT_PBR_GENERATE = "material.pbr_generate"
    MAT_BATCH_REPLACE = "material.batch_replace"
    MAT_BATCH_ADJUST = "material.batch_adjust"
    MAT_PRESET_SAVE = "material.preset_save"
    MAT_PRESET_LOAD = "material.preset_load"
    MAT_DUPLICATE = "material.duplicate"

    # 渲染
    RENDER_SWITCH_ENGINE = "render.switch_engine"
    RENDER_SETTINGS = "render.settings"
    RENDER_EXECUTE = "render.execute"
    RENDER_RESULT_BACK = "render.result_back"

    # 场景 / 备份 / 回滚
    SCENE_BACKUP = "scene.backup"
    SCENE_ROLLBACK = "scene.rollback"
    SCENE_EXPORT = "scene.export"
    SCENE_IMPORT = "scene.import"

    # 反向链路：Blender 数据回传 DSH
    EXPORT_ASSET = "export.asset"
    EXPORT_ANIMATION = "export.animation"
    EXPORT_MATERIAL = "export.material"
    EXPORT_SCENE = "export.scene"

    # 自然语言解析结果下发
    NL_DISPATCH = "nl.dispatch"

    # 端到端流水线
    PIPELINE_CHARACTER = "pipeline.character"
    PIPELINE_VIDEO = "pipeline.video"
    PIPELINE_ITERATE = "pipeline.iterate"

    # 第三方插件生态：识别 / 详情 / 调用 / 意图匹配
    ADDON_LIST = "addon.list"
    ADDON_DETAIL = "addon.detail"
    ADDON_INVOKE = "addon.invoke"
    ADDON_MATCH = "addon.match"


# ---------------------------------------------------------------------------
# 信封构造与校验
# ---------------------------------------------------------------------------
REQUIRED_FIELDS = ("cmd_id", "cmd_type", "payload", "status", "result", "error")


def new_command(cmd_type: str, payload: Optional[Dict[str, Any]] = None,
                cmd_id: Optional[str] = None) -> Dict[str, Any]:
    """构造一条出站指令信封。"""
    return {
        "cmd_id": cmd_id or str(uuid.uuid4()),
        "cmd_type": cmd_type,
        "payload": payload or {},
        "status": STATUS_PENDING,
        "result": {},
        "error": {"code": "", "message": "", "detail": ""},
    }


def make_result(cmd_id: str, cmd_type: str, status: str,
                result: Optional[Dict[str, Any]] = None,
                error: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """构造一条回执信封。"""
    return {
        "cmd_id": cmd_id,
        "cmd_type": cmd_type,
        "payload": {},
        "status": status,
        "result": result or {},
        "error": error or {"code": "", "message": "", "detail": ""},
    }


def validate_envelope(msg: Dict[str, Any]) -> Dict[str, str]:
    """
    校验信封合法性。

    :return: 错误描述字典；空字典表示校验通过
    """
    if not isinstance(msg, dict):
        return {"code": "E_PROTOCOL", "message": "消息体必须为 JSON 对象"}

    missing = [f for f in REQUIRED_FIELDS if f not in msg]
    if missing:
        return {"code": "E_PROTOCOL",
                "message": f"缺少必填字段: {', '.join(missing)}"}

    if not isinstance(msg["cmd_id"], str) or not msg["cmd_id"]:
        return {"code": "E_PROTOCOL", "message": "cmd_id 非法"}
    if not isinstance(msg["cmd_type"], str) or not msg["cmd_type"]:
        return {"code": "E_PROTOCOL", "message": "cmd_type 非法"}
    if not isinstance(msg["payload"], dict):
        return {"code": "E_PROTOCOL", "message": "payload 必须为对象"}
    if msg["status"] not in ALL_STATUS:
        return {"code": "E_PROTOCOL", "message": f"status 非法: {msg['status']}"}
    return {}


def now_ts() -> float:
    """当前时间戳（秒），便于链路时延统计。"""
    return time.time()
