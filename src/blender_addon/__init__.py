# -*- coding: utf-8 -*-
"""
DSH ↔ Blender 双向桥接 Addon 入口。

功能概览：
- 本地 WebSocket 长连接，30s 心跳 / 断线重连 / 状态可视化
- 标准化 JSON 协议，批量指令队列串行 / 并行执行
- 多模态分片传输（断点续传 + MD5 校验）
- 图片建模 / 视频动捕与特效 / 自然语言建模 / 动画 / 材质 / 渲染全链路
- 资产反向回传，支持多轮迭代优化

兼容 Blender 4.2 LTS ~ 5.3，仅依赖 Blender 内置 Python 库。
"""

from __future__ import annotations

import bpy

# 插件元信息（Blender 偏好设置中可见）
bl_info = {
    "name": "DSH Blender Bridge",
    "author": "DSH-Blender Bridge Contributors",
    "version": (1, 1, 9),
    "blender": (4, 2, 0),
    "location": "3D View > Sidebar > DSH Bridge",
    "description": "DSH 与 Blender 双向实时桥接：多模态输入 → AI 解析 → 3D 生产 → 迭代 → 渲染交付",
    "category": "3D View",
    "support": "COMMUNITY",
}

ADDON_VERSION = "1.1.9"


def register() -> None:
    # 1) 初始化运行配置与日志
    from . import addon_state
    cfg = addon_state.init_runtime()
    cfg["addon_version"] = ADDON_VERSION

    # 2) 注册操作符 / 属性组 / 面板
    from . import operators, panel
    operators.register()
    panel.register()

    # 3) 面板属性回填配置
    #    注意：插件 register() 阶段 bpy.data 处于 _RestrictData 受限状态，
    #    直接遍历 bpy.data.scenes 会抛 AttributeError，因此先尝试、失败则延迟到定时器。
    def _sync_panels():
        try:
            for scene in bpy.data.scenes:
                if hasattr(scene, "dsh_bridge"):
                    scene.dsh_bridge.sync_from_config()
        except Exception:  # noqa: BLE001
            pass
        return None  # 只执行一次

    try:
        _sync_panels()
    except Exception:  # noqa: BLE001
        pass
    try:
        bpy.app.timers.register(_sync_panels, first_interval=0.2)
    except Exception:  # noqa: BLE001
        pass


def unregister() -> None:
    # 1) 停止桥接服务与定时器
    from . import addon_state
    addon_state.stop_bridge()

    # 2) 注销 UI
    from . import panel, operators
    panel.unregister()
    operators.unregister()
