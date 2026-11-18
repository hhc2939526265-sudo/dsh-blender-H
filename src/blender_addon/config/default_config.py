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

# 运行期可写目录统一由 utils.paths 收敛到用户目录（DSH_Bridge/...），
# 此处默认留空，加载时按 paths 解析，避免把缓存 / 渲染产物写入 Blender 安装目录。
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
    # 握手共享口令：留空表示不校验（仅本机回环）；非空时客户端须在
    # Sec-WebSocket-Protocol 或 Authorization: Bearer 中携带同一口令
    "auth_token": "",
    # 浏览器网页发起连接时允许的 Origin 主机名（不含协议 / 端口）；
    # 空集合表示仅接受无 Origin 头的本机桌面客户端；localhost / 127.0.0.1 始终放行
    "allowed_origins": [],

    # ---- 分片传输 ----
    "chunk_size": 64 * 1024,         # 单分片字节数（64KB）
    "transfer_dir": "",              # 空 → paths.subdir("transfer")
    "resume_enabled": True,          # 断点续传开关
    "verify_md5": True,              # 接收后 MD5 校验开关
    "max_upload_size_mb": 2048,      # 单文件上传大小上限（MB）

    # ---- 指令执行 ----
    "queue_mode": "serial",          # serial（串行）/ parallel（并行）
    "max_parallel": 2,                # 并行模式下最大并发执行数
    # 指令排队等待超时（秒）：条目在队列中等待超过该时长即被丢弃；
    # 注意 Blender 主线程不可抢占，正在执行的指令无法被中途中断，执行超时
    # 需待后台线程执行模型就绪后落地，当前不提供执行中断能力。
    "command_timeout": 120,
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
    "render_output_dir": "",          # 空 → paths.subdir("render")

    # ---- 日志 ----
    "log_level": "INFO",              # DEBUG / INFO / WARNING / ERROR
    "log_dir": "",                    # 空 → paths.subdir("logs")
    "log_keep_days": 14,              # 日志保留天数

    # ---- 内存管理 ----
    "batch_size": 32,                  # 批量操作分批大小
    "idle_release_seconds": 300,       # 闲置多久后释放临时缓存

    # ---- 第三方插件生态 ----
    "allow_addon_invoke": True,         # 是否允许桥接调用第三方插件算子
    "addon_max_operators_per_addon": 50,  # 单个插件向上暴露的算子数量上限
    # 算子白名单：条目为算子 ID 前缀（如 "object"、"mesh"）；空列表表示不限前缀
    "addon_operator_allowlist": [],
    # 算子黑名单：无论白名单如何配置，命中子串即拒绝（工程 / 脚本 / 控制台等危险算子）
    "addon_operator_denylist": [
        "wm.open_mainfile", "wm.save_mainfile", "wm.read_factory_settings",
        "wm.delete", "file.", "script.", "console.", "bpy.",
    ],
}


def _resolve_dirs(cfg: dict) -> None:
    """把空目录配置项收敛到用户目录（paths 子目录），并确保目录存在。"""
    from ..utils import paths
    dir_map = {
        "transfer_dir": "transfer",
        "render_output_dir": "render",
        "log_dir": "logs",
    }
    for key, subkey in dir_map.items():
        if not cfg.get(key):
            cfg[key] = paths.subdir(subkey)
        else:
            os.makedirs(cfg[key], exist_ok=True)


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
    _resolve_dirs(cfg)
    return cfg


def save_config(cfg: dict) -> None:
    """将运行时配置持久化到本地用户配置文件。"""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(RUNTIME_CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)


def get_default(key: str):
    """读取某一项默认配置。"""
    return DEFAULT_CONFIG.get(key)
