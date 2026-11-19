# -*- coding: utf-8 -*-
"""
插件全局状态单例（Blender 端）。

持有：运行配置、日志器、Bridge 主控实例、主线程定时器句柄。
``__init__.py`` 的 register / unregister 与面板 / 操作符均通过本模块访问，
避免在多处重复构造子系统。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

import bpy

from .config import load_config, save_config
from .utils.logger import get_logger as make_logger
from .core.bridge import Bridge

# 定时器标识
TIMER_NAME = "dsh_bridge_tick"

_state: Dict[str, Any] = {
    "config": None,
    "logger": None,
    "bridge": None,
    "timer_registered": False,
    "tick_fn": None,
}


def init_runtime() -> Dict[str, Any]:
    """加载配置与日志器（插件启用时调用一次）。"""
    cfg = load_config()
    logger = make_logger("dsh_bridge", level=cfg.get("log_level", "INFO"),
                        log_dir=cfg.get("log_dir"),
                        keep_days=int(cfg.get("log_keep_days", 14)))
    _state["config"] = cfg
    _state["logger"] = logger
    return cfg


def get_config() -> Dict[str, Any]:
    if _state["config"] is None:
        init_runtime()
    return _state["config"]


def get_logger():
    if _state["logger"] is None:
        init_runtime()
    return _state["logger"]


def get_bridge() -> Optional[Bridge]:
    return _state["bridge"]


def ensure_bridge() -> Bridge:
    """惰性创建 Bridge 实例。"""
    if _state["bridge"] is None:
        _state["bridge"] = Bridge(get_config(), get_logger())
    return _state["bridge"]


def start_bridge() -> bool:
    """启动桥接并注册主线程定时器。"""
    bridge = ensure_bridge()
    ok = bridge.start()
    if ok and not _state["timer_registered"]:
        tick_fn = bridge.on_main_thread_tick
        _state["tick_fn"] = tick_fn
        bpy.app.timers.register(tick_fn, first_interval=0.1, persistent=True)
        _state["timer_registered"] = True
    return ok


def stop_bridge() -> None:
    """停止桥接并注销定时器。"""
    bridge = _state["bridge"]
    if bridge is not None:
        bridge.stop()
    if _state["timer_registered"] and _state["tick_fn"] is not None:
        try:
            bpy.app.timers.unregister(_state["tick_fn"])
        except (KeyError, ValueError):
            pass
        _state["timer_registered"] = False
        _state["tick_fn"] = None


def restart_bridge() -> bool:
    stop_bridge()
    return start_bridge()


def persist_config() -> None:
    """把当前配置写回本地用户配置文件。"""
    if _state["config"] is not None:
        save_config(_state["config"])
