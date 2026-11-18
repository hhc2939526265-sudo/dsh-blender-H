# -*- coding: utf-8 -*-
"""
AI 解析适配层抽象接口（Blender 端）。

设计目标：
- 业务处理器只依赖 ``BaseAIProvider`` 抽象接口，不关心底层是本地规则兜底、
  内置推理模型还是外部 HTTP 推理服务。
- 所有解析结果均为可 JSON 序列化的纯字典，沿标准协议回传 / 驱动 Blender。
- 新增推理后端只需继承本类并在 ``registry`` 中注册，无需改动业务代码。

规格字典约定（与《开发接口文档》保持一致）：

角色规格 character_spec::

    {
      "quality": "low|medium|high",
      "proportions": {"height": 1.75, "shoulder_width": 0.45, ...},
      "features": {"face": "...", "eyes": "...", "nose": "...", "mouth": "..."},
      "clothing": [{"part": "top", "material": "...", "color": [r,g,b]}, ...],
      "hair": {"style": "short", "color": [r,g,b]},
      "skin_color": [r, g, b],
      "shape_keys": ["jaw_open", "brow_inner_up", ...]
    }

动作规格 motion_spec::

    {
      "fps": 24,
      "joints": ["hips", "spine", "chest", "neck", ... 21+],
      "frames": [{"index": 0, "rotations": {joint: [rx,ry,rz]},
                  "positions": {joint: [x,y,z]}}, ...],
      "confidence": 0.0~1.0,
      "loop": true
    }

特效规格 effect_spec::

    {
      "particles": [{"count": 200, "speed": 1.0, "life": 2.0,
                      "color_start": [...], "color_end": [...]}],
      "glow": [{"intensity": 1.5, "color": [...], "motion": "radial"}],
      "fluid": [{"shape": "smoke", "velocity": 0.6, "collision": true}],
      "deform": [{"target": "obj", "amplitude": 0.2, "timing": [0, 24]}],
      "camera": {"trajectory": "push", "distance": 3.0, "frames": [...]}
    }
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class BaseAIProvider:
    """AI 解析后端抽象基类。"""

    #: 后端唯一标识，供配置项选择
    name: str = "base"

    def analyze_character(self, image_paths: List[str],
                         params: Optional[Dict[str, Any]] = None
                         ) -> Dict[str, Any]:
        """从人物图片解析角色规格。子类必须实现。"""
        raise NotImplementedError

    def analyze_motion(self, video_path: str,
                       params: Optional[Dict[str, Any]] = None
                       ) -> Dict[str, Any]:
        """从动作视频解析骨骼轨迹规格。子类必须实现。"""
        raise NotImplementedError

    def analyze_effect(self, video_path: str,
                       params: Optional[Dict[str, Any]] = None
                       ) -> Dict[str, Any]:
        """从特效视频解析粒子 / 光效 / 流体 / 形变 / 镜头规格。"""
        raise NotImplementedError

    def parse_natural_language(self, prompt: str,
                              params: Optional[Dict[str, Any]] = None
                              ) -> Dict[str, Any]:
        """自然语言提示词解析为指令列表。"""
        raise NotImplementedError
