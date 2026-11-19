# -*- coding: utf-8 -*-
"""
跨平台路径管理（Blender 端）。

- 运行期可写目录（传输缓存 / 渲染输出 / 日志 / 备份 / 预设）统一收敛到
  用户目录下的 ``DSH_Bridge`` 文件夹，避免写入 Blender 安装目录导致权限问题。
- 同时兼容打包后的 Addon 目录布局。
- 全部目录在首次使用时惰性创建，不存在硬编码的绝对用户路径。
"""

from __future__ import annotations

import os
import sys
import tempfile
from typing import Dict


def _home_root() -> str:
    """返回跨平台的用户数据根目录。"""
    base = os.environ.get("DSH_BRIDGE_HOME")
    if base:
        return base
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(appdata, "DSH_Bridge")
    if sys.platform == "darwin":
        return os.path.join(os.path.expanduser("~"),
                            "Library", "Application Support", "DSH_Bridge")
    return os.path.join(os.path.expanduser("~"), ".dsh_bridge")


ROOT_DIR = _home_root()

# 固定子目录名
_SUBDIRS = {
    "config": "config",
    "transfer": "transfer_cache",
    "render": "render_output",
    "logs": "logs",
    "backup": "backups",
    "presets": "presets",
    "temp": "temp",
}


def subdir(key: str) -> str:
    """按逻辑键返回子目录绝对路径，并确保目录存在。"""
    rel = _SUBDIRS.get(key, key)
    path = os.path.join(ROOT_DIR, rel)
    os.makedirs(path, exist_ok=True)
    return path


def all_dirs() -> Dict[str, str]:
    """返回全部运行期目录映射。"""
    return {key: subdir(key) for key in _SUBDIRS}


def temp_path(filename: str) -> str:
    """在临时目录下拼接安全文件名。"""
    return os.path.join(subdir("temp"), os.path.basename(filename))


def safe_name(filename: str) -> str:
    """清洗文件名，剥离路径成分，防止目录穿越；非法名抛 ValueError。"""
    safe = os.path.basename(str(filename or "")).strip()
    if not safe or safe in (".", ".."):
        raise ValueError("文件名非法（为空或包含路径穿越）")
    return safe


def safe_join(subdir_key: str, filename: str) -> str:
    """在指定逻辑子目录下拼接清洗后的安全文件路径。"""
    return os.path.join(subdir(subdir_key), safe_name(filename))


def is_within(base_dir: str, path: str) -> bool:
    """判断路径是否位于 base_dir 目录之内（规范化后比较，防 ../ 穿越）。"""
    base = os.path.abspath(base_dir)
    target = os.path.abspath(path)
    return target == base or target.startswith(base + os.sep)


def require_within(base_dir: str, path: str, what: str = "路径") -> str:
    """校验路径位于允许目录内，越界抛 PermissionError，否则返回规范化路径。"""
    target = os.path.abspath(path)
    if not is_within(base_dir, target):
        raise PermissionError(f"{what}越出允许目录: {path}")
    return target


def cleanup_temp(max_age_seconds: int) -> int:
    """
    清理临时目录中超过保留时长的文件，返回删除数量。

    用于闲置内存 / 磁盘释放策略，避免临时文件长期堆积。
    """
    import time
    temp_dir = subdir("temp")
    now = time.time()
    removed = 0
    try:
        for name in os.listdir(temp_dir):
            path = os.path.join(temp_dir, name)
            try:
                if os.path.isfile(path) and now - os.path.getmtime(path) > max_age_seconds:
                    os.remove(path)
                    removed += 1
            except OSError:
                continue
    except OSError:
        pass
    return removed


def platform_name() -> str:
    """返回当前平台标识：windows / macos / linux。"""
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    return "linux"
