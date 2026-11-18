# -*- coding: utf-8 -*-
"""
分级日志系统（Blender 端）。

- 四级：DEBUG / INFO / WARNING / ERROR
- 同时输出到 Blender 控制台与本地日志文件（按天滚动）
- 线程安全：后台 WebSocket 线程与主线程均可写入
- 支持日志保留天数清理
"""

from __future__ import annotations

import os
import logging
import datetime
import threading
from logging.handlers import TimedRotatingFileHandler

# 日志级别映射
_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}

_logger_cache = {}
_lock = threading.Lock()


def _clean_old_logs(log_dir: str, keep_days: int) -> None:
    """删除超过保留天数的历史日志文件。"""
    if not os.path.isdir(log_dir):
        return
    cutoff = datetime.datetime.now() - datetime.timedelta(days=keep_days)
    for name in os.listdir(log_dir):
        path = os.path.join(log_dir, name)
        try:
            mtime = datetime.datetime.fromtimestamp(os.path.getmtime(path))
            if mtime < cutoff:
                os.remove(path)
        except OSError:
            continue


def get_logger(name: str = "dsh_bridge", level: str = "INFO",
               log_dir: str | None = None) -> logging.Logger:
    """
    获取（带缓存的）命名日志器。

    :param name: 日志器名称
    :param level: 日志级别字符串
    :param log_dir: 日志目录，为空则不写文件
    :return: 配置完成的 logging.Logger
    """
    with _lock:
        if name in _logger_cache:
            return _logger_cache[name]

        logger = logging.getLogger(name)
        logger.setLevel(_LEVEL_MAP.get(level.upper(), logging.INFO))
        logger.propagate = False

        # 控制台输出
        if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
            console = logging.StreamHandler()
            console.setFormatter(
                logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s",
                                  datefmt="%Y-%m-%d %H:%M:%S"))
            logger.addHandler(console)

        # 文件输出（按天滚动）
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
            _clean_old_logs(log_dir, keep_days=14)
            if not any(isinstance(h, TimedRotatingFileHandler) for h in logger.handlers):
                file_handler = TimedRotatingFileHandler(
                    os.path.join(log_dir, f"{name}.log"),
                    when="midnight", backupCount=14, encoding="utf-8")
                file_handler.setFormatter(
                    logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s",
                                      datefmt="%Y-%m-%d %H:%M:%S"))
                logger.addHandler(file_handler)

        _logger_cache[name] = logger
        return logger
