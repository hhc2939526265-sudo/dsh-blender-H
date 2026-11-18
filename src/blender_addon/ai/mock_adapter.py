# -*- coding: utf-8 -*-
"""
本地确定性兜底解析器（Mock Provider）。

在未接入外部推理服务、或外部服务不可用时提供可复现的规格输出：
- 角色规格：按图片数量与精度档位生成标准化人体比例 / 服装分层 / 发型 / 表情单元
- 动作规格：生成一套可循环的基础走姿骨骼轨迹（21 关节）
- 特效规格：生成一组参数化粒子 / 辉光 / 流体 / 形变 / 镜头默认规格
- 自然语言：基于中文关键词规则映射到内置建模 / 动画 / 材质指令

输出结果完全确定性（同参数同结果），便于演示案例复现与单元测试。
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional

from .base import BaseAIProvider


# 标准人形 21 关节命名（与骨骼命名一一对应）
STANDARD_JOINTS: List[str] = [
    "hips", "spine", "chest", "neck", "head",
    "left_clavicle", "left_upper_arm", "left_forearm", "left_hand",
    "right_clavicle", "right_upper_arm", "right_forearm", "right_hand",
    "left_thigh", "left_shin", "left_foot",
    "right_thigh", "right_shin", "right_foot",
    "root", "toe_left", "toe_right",
]

# 50+ 面部基础形状键清单
FACE_SHAPE_KEYS: List[str] = [
    "brow_down_left", "brow_down_right", "brow_inner_up", "brow_outer_up_left",
    "brow_outer_up_right", "eye_blink_left", "eye_blink_right", "eye_look_up",
    "eye_look_down", "eye_look_in_left", "eye_look_in_right", "eye_squint_left",
    "eye_squint_right", "eye_wide_left", "eye_wide_right", "nose_nose",
    "nose_sneer_left", "nose_sneer_right", "mouth_funnel", "mouth_left",
    "mouth_right", "mouth_lower_down_left", "mouth_lower_down_right",
    "mouth_pucker", "mouth_roll_lower", "mouth_roll_upper", "mouth_shrug_lower",
    "mouth_shrug_upper", "mouth_smile_left", "mouth_smile_right", "mouth_stretch_left",
    "mouth_stretch_right", "mouth_upper_up_left", "mouth_upper_up_right",
    "jaw_forward", "jaw_left", "jaw_right", "jaw_open", "cheek_puff",
    "cheek_squint_left", "cheek_squint_right", "tongue_out", "tongue_up",
    "tongue_down", "tongue_left", "tongue_right", "frown_left", "frown_right",
    "grimace", "puff_left", "puff_right", "blink_doubled",
]


class MockAIProvider(BaseAIProvider):
    """规则驱动的本地兜底解析器。"""

    name = "mock"

    # ------------------------------------------------------------- 角色
    def analyze_character(self, image_paths: List[str],
                         params: Optional[Dict[str, Any]] = None
                         ) -> Dict[str, Any]:
        params = params or {}
        quality = params.get("quality", "medium")
        # 依据图片数量做保守比例估计（多张照片取均值占位，外部服务接入后替换）
        photo_count = max(1, len(image_paths))
        return {
            "quality": quality,
            "source_images": list(image_paths),
            "proportions": {
                "height": 1.75,
                "shoulder_width": 0.45,
                "hip_width": 0.30,
                "torso_length": 0.55,
                "leg_ratio": 0.52,
                "photo_count": photo_count,
            },
            "features": {
                "face": "oval",
                "eyes": "normal",
                "nose": "normal",
                "mouth": "normal",
                "eyebrows": "normal",
            },
            "clothing": [
                {"part": "top", "category": "hard_surface",
                 "color": [0.32, 0.36, 0.42], "roughness": 0.7},
                {"part": "bottom", "category": "cloth",
                 "color": [0.18, 0.18, 0.20], "roughness": 0.85},
                {"part": "shoes", "category": "hard_surface",
                 "color": [0.08, 0.08, 0.09], "roughness": 0.4},
            ],
            "hair": {"style": "short", "color": [0.05, 0.04, 0.03]},
            "skin_color": [0.82, 0.66, 0.55],
            "shape_keys": FACE_SHAPE_KEYS,
        }

    # ------------------------------------------------------------- 动作
    def analyze_motion(self, video_path: str,
                       params: Optional[Dict[str, Any]] = None
                       ) -> Dict[str, Any]:
        params = params or {}
        fps = int(params.get("fps", 24))
        duration = float(params.get("duration", 1.0))
        frame_count = max(2, int(round(fps * duration)))
        confidence = float(params.get("confidence", 0.6))

        frames: List[Dict[str, Any]] = []
        for i in range(frame_count):
            phase = 2.0 * math.pi * i / frame_count
            # 周期性走姿：髋部 / 大腿 / 小腿前后摆动，手臂反向摆动
            rot: Dict[str, List[float]] = {}
            pos: Dict[str, List[float]] = {}
            rot["hips"] = [0.0, 0.0, math.sin(phase) * 0.03]
            rot["spine"] = [0.0, 0.0, 0.0]
            rot["chest"] = [0.0, 0.0, 0.0]
            rot["neck"] = [0.05 * math.sin(phase), 0.0, 0.0]
            rot["head"] = [0.0, 0.0, 0.02 * math.sin(phase)]
            rot["left_upper_arm"] = [0.4 * math.sin(phase + math.pi), 0.0, 0.0]
            rot["right_upper_arm"] = [0.4 * math.sin(phase), 0.0, 0.0]
            rot["left_forearm"] = [0.3, 0.0, 0.0]
            rot["right_forearm"] = [0.3, 0.0, 0.0]
            rot["left_thigh"] = [0.5 * math.sin(phase), 0.0, 0.0]
            rot["right_thigh"] = [0.5 * math.sin(phase + math.pi), 0.0, 0.0]
            rot["left_shin"] = [-0.3 * max(0.0, math.sin(phase)), 0.0, 0.0]
            rot["right_shin"] = [-0.3 * max(0.0, math.sin(phase + math.pi)), 0.0, 0.0]
            pos["hips"] = [0.0, 0.0, 0.9 + 0.02 * abs(math.sin(phase))]
            frames.append({"index": i, "rotations": rot, "positions": pos})

        return {
            "fps": fps,
            "joints": STANDARD_JOINTS,
            "frames": frames,
            "confidence": confidence,
            "loop": True,
            "source_video": video_path,
        }

    # ------------------------------------------------------------- 特效
    def analyze_effect(self, video_path: str,
                       params: Optional[Dict[str, Any]] = None
                       ) -> Dict[str, Any]:
        strength = float((params or {}).get("effect_strength", 0.8))
        return {
            "source_video": video_path,
            "particles": [{
                "name": "main_particles",
                "count": int(200 * strength),
                "speed": 1.0 * strength,
                "life": 2.0,
                "size": 0.05,
                "color_start": [1.0, 0.6, 0.2],
                "color_end": [0.2, 0.4, 1.0],
            }],
            "glow": [{
                "name": "main_glow",
                "intensity": 1.5 * strength,
                "color": [1.0, 0.7, 0.3],
                "motion": "radial",
            }],
            "fluid": [{
                "name": "main_fluid",
                "shape": "smoke",
                "velocity": 0.6 * strength,
                "collision": True,
            }],
            "deform": [{
                "name": "main_deform",
                "amplitude": 0.2 * strength,
                "timing": [0, 24],
            }],
            "camera": {"trajectory": "push", "distance": 3.0,
                       "fov": 50.0, "frames": []},
        }

    # ------------------------------------------------------------- 自然语言
    def parse_natural_language(self, prompt: str,
                               params: Optional[Dict[str, Any]] = None
                               ) -> Dict[str, Any]:
        """
        中文关键词规则解析：把提示词映射为指令序列。

        规则表覆盖常见建模 / 动画 / 材质意图；未命中时返回空指令列表，
        由上层提示用户补充描述。接入外部大模型后可整体替换本方法。
        """
        text = prompt.lower()
        commands: List[Dict[str, Any]] = []

        def add(cmd_type: str, payload: Dict[str, Any]) -> None:
            commands.append({"cmd_type": cmd_type, "payload": payload})

        # 几何体识别
        geom_map = {
            "立方体": "cube", "方块": "cube", "球体": "sphere",
            "圆柱": "cylinder", "圆锥": "cone", "圆环": "torus",
            "平面": "plane", "猴头": "monkey",
        }
        for kw, ptype in geom_map.items():
            if kw in text:
                add("mesh.add_primitive", {"type": ptype, "name": f"nl_{ptype}"})
                break

        if "倒角" in text:
            add("mesh.bevel", {"object": "active", "width": 0.05, "segments": 3})
        if "阵列" in text:
            add("mesh.array", {"object": "active", "count": 3})
        if "细分" in text:
            add("mesh.subdivide", {"object": "active", "levels": 1})
        if "精简" in text or "减面" in text:
            add("mesh.decimate", {"object": "active", "ratio": 0.5})
        if "对齐地面" in text or "原点" in text:
            add("mesh.origin_set", {"object": "active"})
        if "平滑" in text:
            add("mesh.smooth", {"object": "active"})
        if "复制" in text or "拷贝" in text:
            add("mesh.duplicate", {"object": "active", "linked": False})
        if "合并" in text:
            add("mesh.join", {"object": "active", "objects": []})
        if "线框" in text:
            add("mesh.wireframe", {"object": "active", "thickness": 0.02})
        if "起伏" in text or "置换" in text:
            add("mesh.displace", {"object": "active", "strength": 0.2})

        # 动画意图
        if "旋转" in text:
            add("anim.keyframe", {"object": "active", "mode": "rotation",
                                  "frames": [[0, [0, 0, 0]], [24, [0, 0, 360]]]})
        if "移动" in text or "位移" in text:
            add("anim.keyframe", {"object": "active", "mode": "location",
                                  "frames": [[0, [0, 0, 0]], [24, [2, 0, 0]]]})
        if "循环动画" in text or "走" in text:
            add("anim.loop_cycle", {"object": "active", "cycle": "walk"})

        # 材质意图
        if "金属" in text:
            add("material.pbr_generate", {"object": "active",
                                         "metallic": 0.9, "roughness": 0.25})
        elif "布料" in text or "织物" in text:
            add("material.pbr_generate", {"object": "active",
                                         "metallic": 0.0, "roughness": 0.85})
        elif "玻璃" in text:
            add("material.pbr_generate", {"object": "active",
                                         "metallic": 0.0, "roughness": 0.1,
                                         "alpha": 0.35})

        # 特效意图
        if "毛发" in text or "头发" in text:
            add("effect.hair", {"object": "active",
                                 "hair": {"count": 500, "length": 0.15}})
        if "灯光" in text or "补光" in text or "聚光" in text:
            add("effect.light", {"type": "POINT", "energy": 100.0,
                                 "color": [1.0, 0.9, 0.8, 1.0]})
        if "风场" in text or "风力" in text:
            add("effect.force_field", {"object": "active", "kind": "WIND",
                                       "field": {"strength": 1.0}})
        if "剑气" in text or "拖尾" in text or "残影" in text:
            add("effect.trail", {"object": "active",
                                 "trail": {"length": 0.6, "width": 0.02}})
        if "护盾" in text or "结界" in text:
            add("effect.shield", {"object": "active",
                                  "shield": {"radius": 0.8, "alpha": 0.25}})
        if "雷" in text or "闪电" in text:
            add("effect.lightning", {"start": [0.0, -1.0, 2.0],
                                     "end": [0.0, 1.0, 1.2], "segments": 8})
        if "灵气" in text or "光环" in text:
            add("effect.aura", {"object": "active", "aura": {"radius": 0.6}})
        if "冲击波" in text or "气浪" in text:
            add("effect.shockwave", {"object": "active",
                                     "shockwave": {"timing": [12, 24], "max_radius": 2.0}})
        if "火花" in text:
            add("effect.spark", {"object": "active", "spark": {"count": 120}})
        if "碎片" in text or "碎石" in text:
            add("effect.debris", {"object": "active", "debris": {"count": 12}})
        if "震动" in text or "震屏" in text:
            add("effect.camera_shake", {"amplitude": 0.08, "end_frame": 24})

        # 常用插件概念映射（与内置目录条目对应）
        if "布料物理" in text or "服装物理" in text or "衣料" in text:
            add("anim.physics", {"object": "active", "kind": "cloth", "mass": 0.5})
        if "软体" in text or "抖动" in text or "摆动" in text:
            add("anim.physics", {"object": "active", "kind": "soft", "mass": 1.0})
        if "地形" in text or "山地" in text or "地貌" in text:
            add("mesh.subdivide", {"object": "active", "levels": 2})
            add("mesh.displace", {"object": "active", "strength": 0.3})
        if "散布" in text or "植被" in text:
            add("mesh.batch_generate", {"count": 20, "type": "cube",
                                        "name_prefix": "scatter"})
        if "烘焙" in text or "法线贴图" in text or "ao" in text:
            add("character.uv_bake", {"object": "active"})
        if "自动绑定" in text or "骨骼绑定" in text:
            add("anim.rig_auto", {"object": "active"})
        if "表情" in text or "面部" in text:
            add("character.shape_keys", {"object": "active"})
        if "岩石" in text or "岩体" in text:
            add("mesh.displace", {"object": "active", "strength": 0.25})
        if "风格化" in text or "卡通" in text:
            add("material.pbr_generate", {"object": "active", "stylized": True})

        return {"prompt": prompt, "commands": commands,
                "matched_rules": len(commands)}
