# -*- coding: utf-8 -*-
"""
AI 提供者注册表（Blender 端）。

- 按配置项 ``ai.provider`` 选择后端：``mock``（本地兜底）/ ``http``（远端网关）
- 远端后端初始化失败或运行期不可用时，自动降级到 Mock，并写入警告日志，
  保证插件在离线环境下依然可演示、可运行。
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from .base import BaseAIProvider
from .mock_adapter import MockAIProvider
from .http_adapter import HTTPAIProvider, AIProviderError


class ProviderRegistry:
    """提供者单例注册表。"""

    def __init__(self, config: Dict[str, Any], logger=None):
        self.config = config or {}
        self.log = logger
        self._fallback = MockAIProvider()
        self._active: Optional[BaseAIProvider] = None
        self._active_name = "mock"
        self._configure()

    def _configure(self) -> None:
        ai_cfg = self.config.get("ai", {}) or {}
        provider_name = str(ai_cfg.get("provider", "mock")).lower()
        if provider_name == "http":
            try:
                self._active = HTTPAIProvider(
                    endpoint=str(ai_cfg.get("endpoint", "http://127.0.0.1:9000/ai")),
                    timeout=float(ai_cfg.get("timeout", 15.0)),
                    api_key=str(ai_cfg.get("api_key", "")),
                )
                self._active_name = "http"
                return
            except (ValueError, TypeError) as exc:
                self._warn(f"HTTP 推理后端初始化失败，降级 Mock: {exc}")
        self._active = self._fallback
        self._active_name = "mock"

    def _warn(self, msg: str) -> None:
        if self.log is not None:
            getattr(self.log, "warning", self.log.info)(msg)

    @property
    def active_name(self) -> str:
        return self._active_name

    def provider(self) -> BaseAIProvider:
        """返回当前可用提供者；远端异常时当场降级。"""
        return self._active

    def safe_call(self, method: str, *args, **kwargs) -> Dict[str, Any]:
        """
        调用当前提供者的指定方法；远端失败时自动回退 Mock 同名方法。

        :return: (结果字典, 实际提供者名)
        """
        try:
            fn = getattr(self._active, method)
            return fn(*args, **kwargs), self._active_name
        except AIProviderError as exc:
            self._warn(f"远端推理失败，降级 Mock: {exc}")
            fn = getattr(self._fallback, method)
            return fn(*args, **kwargs), "mock"
