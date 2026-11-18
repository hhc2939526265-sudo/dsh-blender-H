# -*- coding: utf-8 -*-
"""
Blender 操作符与属性组（Blender 端）。

- 桥接服务启动 / 停止 / 重启 / 状态刷新 / 队列清空
- 面板可配置项属性组，与运行配置双向同步
"""

from __future__ import annotations

import bpy
from bpy.props import (BoolProperty, EnumProperty, IntProperty,
                       StringProperty, FloatProperty)

from . import addon_state


# ---------------------------------------------------------------------------
# 属性组
# ---------------------------------------------------------------------------
class DSHBRIDGE_PG_settings(bpy.types.PropertyGroup):
    """面板参数配置（写入运行配置并持久化）。"""

    host: StringProperty(name="监听地址", default="127.0.0.1")
    port: IntProperty(name="通信端口", default=8765, min=1024, max=65535)
    heartbeat: IntProperty(name="心跳间隔(秒)", default=30, min=5, max=120)
    quality: EnumProperty(
        name="建模精度", items=[("low", "低", "低面数"),
                              ("medium", "中", "平衡"),
                              ("high", "高", "高精度")], default="medium")
    fps: IntProperty(name="动画帧率", default=24, min=12, max=120)
    samples: IntProperty(name="渲染采样", default=64, min=8, max=4096)
    engine: EnumProperty(
        name="渲染引擎", items=[("EEVEE", "Eevee", "实时渲染"),
                              ("CYCLES", "Cycles", "光线追踪")], default="EEVEE")
    log_level: EnumProperty(
        name="日志级别", items=[("DEBUG", "调试", ""), ("INFO", "信息", ""),
                              ("WARNING", "警告", ""), ("ERROR", "错误", "")],
        default="INFO")
    auto_backup: BoolProperty(name="操作前自动备份", default=True)

    def sync_to_config(self) -> None:
        """把面板属性写入运行配置。"""
        cfg = addon_state.get_config()
        cfg["host"] = self.host
        cfg["port"] = self.port
        cfg["heartbeat_interval"] = self.heartbeat
        cfg["mesh_quality"] = self.quality
        cfg["animation_fps"] = self.fps
        cfg["render_samples"] = self.samples
        cfg["render_engine"] = "CYCLES" if self.engine == "CYCLES" else "BLENDER_EEVEE"
        cfg["log_level"] = self.log_level
        cfg["auto_backup"] = self.auto_backup
        addon_state.persist_config()

    def sync_from_config(self) -> None:
        """从运行配置回填面板属性。"""
        cfg = addon_state.get_config()
        self.host = cfg.get("host", "127.0.0.1")
        self.port = int(cfg.get("port", 8765))
        self.heartbeat = int(cfg.get("heartbeat_interval", 30))
        self.quality = cfg.get("mesh_quality", "medium")
        self.fps = int(cfg.get("animation_fps", 24))
        self.samples = int(cfg.get("render_samples", 64))
        self.engine = "CYCLES" if cfg.get("render_engine") == "CYCLES" else "EEVEE"
        self.log_level = cfg.get("log_level", "INFO")
        self.auto_backup = bool(cfg.get("auto_backup", True))


# ---------------------------------------------------------------------------
# 操作符
# ---------------------------------------------------------------------------
class DSHBRIDGE_OT_start(bpy.types.Operator):
    """启动 DSH ↔ Blender 桥接服务"""
    bl_idname = "dsh_bridge.start"
    bl_label = "启动桥接服务"
    bl_options = {"REGISTER"}

    def execute(self, context: bpy.types.Context) -> set:
        context.scene.dsh_bridge.sync_to_config()
        ok = addon_state.start_bridge()
        if ok:
            self.report({"INFO"}, "桥接服务已启动")
        else:
            self.report({"ERROR"}, "端口绑定失败，请检查端口是否被占用")
        return {"FINISHED"} if ok else {"CANCELLED"}


class DSHBRIDGE_OT_stop(bpy.types.Operator):
    """停止桥接服务"""
    bl_idname = "dsh_bridge.stop"
    bl_label = "停止桥接服务"
    bl_options = {"REGISTER"}

    def execute(self, context: bpy.types.Context) -> set:
        addon_state.stop_bridge()
        self.report({"INFO"}, "桥接服务已停止")
        return {"FINISHED"}


class DSHBRIDGE_OT_restart(bpy.types.Operator):
    """重启桥接服务"""
    bl_idname = "dsh_bridge.restart"
    bl_label = "重启桥接服务"
    bl_options = {"REGISTER"}

    def execute(self, context: bpy.types.Context) -> set:
        context.scene.dsh_bridge.sync_to_config()
        ok = addon_state.restart_bridge()
        self.report({"INFO"}, "桥接服务已重启" if ok else "重启失败")
        return {"FINISHED"} if ok else {"CANCELLED"}


class DSHBRIDGE_OT_refresh(bpy.types.Operator):
    """刷新连接状态"""
    bl_idname = "dsh_bridge.refresh"
    bl_label = "刷新状态"
    bl_options = {"REGISTER"}

    def execute(self, context: bpy.types.Context) -> set:
        bridge = addon_state.get_bridge()
        if bridge is not None:
            context.scene.dsh_bridge_status = str(bridge.status())
        return {"FINISHED"}


class DSHBRIDGE_OT_clear_queue(bpy.types.Operator):
    """清空待执行指令队列"""
    bl_idname = "dsh_bridge.clear_queue"
    bl_label = "清空指令队列"
    bl_options = {"REGISTER"}

    def execute(self, context: bpy.types.Context) -> set:
        bridge = addon_state.get_bridge()
        if bridge is not None:
            n = bridge.queue.clear()
            self.report({"INFO"}, f"已清空 {n} 条排队指令")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# 注册
# ---------------------------------------------------------------------------
_CLASSES = (
    DSHBRIDGE_PG_settings,
    DSHBRIDGE_OT_start,
    DSHBRIDGE_OT_stop,
    DSHBRIDGE_OT_restart,
    DSHBRIDGE_OT_refresh,
    DSHBRIDGE_OT_clear_queue,
)


def register() -> None:
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.dsh_bridge = bpy.props.PointerProperty(type=DSHBRIDGE_PG_settings)
    bpy.types.Scene.dsh_bridge_status = bpy.props.StringProperty(
        name="桥接状态", default="{}")


def unregister() -> None:
    del bpy.types.Scene.dsh_bridge_status
    del bpy.types.Scene.dsh_bridge
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
