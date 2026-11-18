# -*- coding: utf-8 -*-
"""配置层：默认配置、运行时配置读写。"""

from .default_config import (  # noqa: F401
    DEFAULT_CONFIG, load_config, save_config, get_default,
    RUNTIME_CONFIG_PATH, CONFIG_DIR,
)
