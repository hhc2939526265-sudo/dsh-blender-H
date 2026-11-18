# -*- coding: utf-8 -*-
"""
外部 HTTP 推理服务适配器（Blender 端）。

通过标准库 ``urllib`` 向本地 / 内网推理网关发送 JSON 请求，不引入第三方依赖。
请求 / 响应报文格式见《开发接口文档》「外部 AI 服务对接」一节。

注意：本适配器只负责协议收发，不内置任何模型权重；服务端不可达时抛出
``AIProviderError``，由注册层自动降级到本地 Mock 兜底。
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional

from .base import BaseAIProvider


class AIProviderError(Exception):
    """推理服务调用失败（网络 / 超时 / 报文非法）。"""


class HTTPAIProvider(BaseAIProvider):
    """远端推理网关适配器。"""

    name = "http"

    def __init__(self, endpoint: str, timeout: float = 15.0,
                 api_key: str = ""):
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key

    # ------------------------------------------------------------- 通用请求
    def _post(self, method: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps({"method": method, "payload": payload},
                          ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self.endpoint, data=body, method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"})
        if self.api_key:
            req.add_header("Authorization", f"Bearer {self.api_key}")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AIProviderError(f"推理服务连接失败: {exc}") from exc

        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise AIProviderError("推理服务返回非法 JSON") from exc

        if not isinstance(data, dict):
            raise AIProviderError("推理服务响应结构非法")
        if data.get("error"):
            raise AIProviderError(str(data["error"]))
        return data.get("result") or data

    # ------------------------------------------------------------- 接口实现
    def analyze_character(self, image_paths: List[str],
                         params: Optional[Dict[str, Any]] = None
                         ) -> Dict[str, Any]:
        return self._post("analyze_character",
                          {"images": image_paths, "params": params or {}})

    def analyze_motion(self, video_path: str,
                       params: Optional[Dict[str, Any]] = None
                       ) -> Dict[str, Any]:
        return self._post("analyze_motion",
                          {"video": video_path, "params": params or {}})

    def analyze_effect(self, video_path: str,
                       params: Optional[Dict[str, Any]] = None
                       ) -> Dict[str, Any]:
        return self._post("analyze_effect",
                          {"video": video_path, "params": params or {}})

    def parse_natural_language(self, prompt: str,
                              params: Optional[Dict[str, Any]] = None
                              ) -> Dict[str, Any]:
        return self._post("parse_nl",
                          {"prompt": prompt, "params": params or {}})
