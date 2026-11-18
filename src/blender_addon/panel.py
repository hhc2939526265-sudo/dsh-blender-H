# -*- coding: utf-8 -*-
"""
DSH Bridge 侧边栏面板（Blender 端）。

位于 3D 视图侧边栏「DSH Bridge」标签页：
- 连接状态指示灯 / 连接数 / 排队指令 / 累计统计
- 启动 / 停止 / 重启 / 刷新 / 清空队列按钮
- 建模精度、帧率、采样、引擎、日志级别等参数配置
"""

from __future__ import annotations

import json
import bpy

from . import addon_state


class DSHBRIDGE_PT_panel(bpy.types.Panel):
    bl_label = "DSH Bridge"
    bl_idname = "DSHBRIDGE_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "DSH Bridge"

    def draw(self, context: bpy.types.Context) -> None:
        layout = self.layout
        settings = context.scene.dsh_bridge
        bridge = addon_state.get_bridge()

        # ---- 状态区 ----
        box = layout.box()
        box.label(text="连接状态", icon="LINKED" if bridge and bridge.is_running() else "UNLINKED")
        if bridge is not None:
            status = bridge.status()
            col = box.column(align=True)
            col.label(text=f"运行中: {'是' if status['running'] else '否'}")
            col.label(text=f"连接数: {status['connections']}  排队: {status['pending']}")
            col.label(text=f"成功: {status['stats']['success']}  失败: {status['stats']['failed']}")
            col.label(text=f"AI 后端: {status['provider']}  端口: {status['port']}")
        else:
            box.label(text="桥接未初始化")

        # ---- 操作按钮 ----
        row = layout.row(align=True)
        row.operator("dsh_bridge.start", icon="PLAY")
        row.operator("dsh_bridge.stop", icon="PAUSE")
        row = layout.row(align=True)
        row.operator("dsh_bridge.restart", icon="REFRESH")
        row.operator("dsh_bridge.clear_queue", icon="TRASH")

        # ---- 参数配置 ----
        box = layout.box()
        box.label(text="参数配置")
        col = box.column(align=True)
        col.prop(settings, "host")
        col.prop(settings, "port")
        col.prop(settings, "heartbeat")
        col.separator()
        col.prop(settings, "quality")
        col.prop(settings, "fps")
        col.prop(settings, "samples")
        col.prop(settings, "engine")
        col.prop(settings, "log_level")
        col.prop(settings, "auto_backup")

        # ---- 指令数量提示 ----
        if bridge is not None:
            layout.box().label(
                text=f"已注册指令: {len(bridge.dispatcher.available_commands())} 种")


def register() -> None:
    bpy.utils.register_class(DSHBRIDGE_PT_panel)


def unregister() -> None:
    bpy.utils.unregister_class(DSHBRIDGE_PT_panel)
