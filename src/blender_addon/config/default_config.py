# -*- coding: utf-8 -*-
"""
全局默认配置（Blender 端）。

所有可调参数集中在本文件，禁止在业务代码中硬编码魔法数字。
用户在面板上修改的配置会写入 ``config/runtime_config.json``，
运行时以「用户配置 > 默认配置」的优先级合并。
"""

from __future__ import annotations

import os
import json

# ---------------------------------------------------------------------------
# 配置文件定位
# ---------------------------------------------------------------------------
ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ADDON_DIR, "config")
RUNTIME_CONFIG_PATH = os.path.join(CONFIG_DIR, "runtime_config.json")

# ---------------------------------------------------------------------------
# 默认配置项
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {
    # ---- 通信 ----
    "host": "127.0.0.1",            # 监听地址，仅本地回环，避免对外暴露
    "port": 8765,                   # 通信端口
    "heartbeat_interval": 30,       # 心跳间隔（秒）
    "heartbeat_timeout": 10,         # 心跳等待 pong 超时（秒）
    "max_reconnect_backoff": 30,     # 对端重连退避上限（秒）
    "max_connections": 4,            # 最大并发连接数

    # ---- 分片传输 ----
    "chunk_size": 64 * 1024,         # 单分片字节数（64KB）
    "transfer_dir": os.path.join(ADDON_DIR, "transfer_cache"),
    "resume_enabled": True,          # 断点续传开关
    "verify_md5": True,              # 接收后 MD5 校验开关

    # ---- 指令执行 ----
    "queue_mode": "serial",          # serial（串行）/ parallel（并行）
    "max_parallel": 2,                # 并行模式下最大并发执行数
    "command_timeout": 120,           # 单条指令超时（秒）
    "auto_backup": True,              # 复杂操作前自动备份场景
    "max_backup_slots": 5,            # 场景备份槽位上限（环形覆盖）

    # ---- 建模 / 动画 / 渲染默认值 ----
    "mesh_quality": "medium",         # low / medium / high
    "mocap_confidence": 0.6,         # 动作捕捉置信度阈值 0~1
    "effect_strength": 0.8,           # 特效还原强度 0~1
    "animation_fps": 24,              # 动画帧率
    "render_engine": "BLENDER_EEVEE", # BLENDER_EEVEE / CYCLES
    "render_resolution": [1920, 1080],
    "render_samples": 64,
    "render_output_dir": os.path.join(ADDON_DIR, "render_output"),

    # ---- 日志 ----
    "log_level": "INFO",              # DEBUG / INFO / WARNING / ERROR
    "log_dir": os.path.join(ADDON_DIR, "logs"),
    "log_keep_days": 14,              # 日志保留天数

    # ---- 内存管理 ----
    "batch_size": 32,                  # 批量操作分批大小
    "idle_release_seconds": 300,       # 闲置多久后释放临时缓存

    # ---- 第三方插件生态 ----
    "allow_addon_invoke": True,         # 是否允许桥接调用第三方插件算子
    "addon_max_operators_per_addon": 50,  # 单个插件向上暴露的算子数量上限
}


def _ensure_dirs(cfg: dict) -> None:
    """确保运行时需要的目录存在。"""
    for key in ("transfer_dir", "render_output_dir", "log_dir"):
        path = cfg.get(key)
        if path:
            os.makedirs(path, exist_ok=True)


def load_config() -> dict:
    """
    加载配置：默认配置 + 本地用户配置覆盖。

    :return: 合并后的配置字典
    """
    cfg = dict(DEFAULT_CONFIG)
    try:
        if os.path.isfile(RUNTIME_CONFIG_PATH):
            with open(RUNTIME_CONFIG_PATH, "r", encoding="utf-8") as fh:
                user_cfg = json.load(fh)
            if isinstance(user_cfg, dict):
                cfg.update(user_cfg)
    except (OSError, ValueError):
        # 配置文件损坏时回退到默认配置，不阻断插件加载
        cfg = dict(DEFAULT_CONFIG)
    _ensure_dirs(cfg)
    return cfg


def save_config(cfg: dict) -> None:
    """将运行时配置持久化到本地用户配置文件。"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(RUNTIME_CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)


def get_default(key: str):
    """读取某一项默认配置。"""
    return DEFAULT_CONFIG.get(key)
