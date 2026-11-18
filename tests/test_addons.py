# -*- coding: utf-8 -*-
"""第三方插件分类 / 匹配 / 参数清洗 纯函数测试（标准库，无需 Blender）。"""

import sys
import types
import os
import unittest

# 未安装 Blender 的环境下注入空 bpy 桩，使模块可导入；纯函数不触达 bpy
sys.modules.setdefault("bpy", types.ModuleType("bpy"))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "blender_addon"))

from handlers import addons  # noqa: E402


class TestClassify(unittest.TestCase):

    def test_rigging_by_keyword(self):
        cap = addons.classify_addon("Rigify Pro", "自动骨骼绑定与权重蒙皮", "Rigging")
        self.assertEqual(cap, "rigging")

    def test_modeling_by_description(self):
        cap = addons.classify_addon("RetopoTool", "自动拓扑布线与网格优化", "Mesh")
        self.assertEqual(cap, "modeling")

    def test_category_fallback_io(self):
        cap = addons.classify_addon("FBX Exporter", "", "Import-Export")
        self.assertEqual(cap, "io")

    def test_unknown_is_other(self):
        cap = addons.classify_addon("随机小工具", "一些杂项功能", "3D View")
        self.assertEqual(cap, "other")


class TestMatch(unittest.TestCase):

    def test_match_rigging_intent(self):
        addon = {
            "name": "骨骼绑定助手", "description": "自动绑定骨骼与权重",
            "category": "Rigging", "capability": "rigging",
            "operator_labels": ["生成骨骼", "分配权重"],
        }
        score, matched = addons.match_score("帮我自动绑定骨骼并分配权重", addon)
        self.assertGreater(score, 0)
        self.assertIn("骨骼", matched)

    def test_no_overlap_score_zero(self):
        addon = {"name": "流体烟雾", "description": "粒子流体特效",
                 "category": "", "capability": "effects", "operator_labels": []}
        score, _ = addons.match_score("金属材质抛光", addon)
        self.assertEqual(score, 0)


class TestSanitize(unittest.TestCase):

    def test_allowed_scalars_and_list(self):
        cleaned = addons._sanitize_params({
            "count": 8, "name": "Cube", "size": 1.5, "use_mirror": True,
            "coords": [1, 2, 3],
        })
        self.assertEqual(cleaned["count"], 8)
        self.assertEqual(cleaned["coords"], [1, 2, 3])

    def test_reject_nested_object(self):
        with self.assertRaises(ValueError):
            addons._sanitize_params({"nested": {"a": 1}})


if __name__ == "__main__":
    unittest.main()
