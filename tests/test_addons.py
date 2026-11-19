# -*- coding: utf-8 -*-
"""第三方插件分类 / 匹配 / 参数清洗 纯函数测试（标准库，无需 Blender）。"""

import sys
import types
import os
import unittest

# 未安装 Blender 的环境下注入最小 bpy 桩（与 test_handlers_guards 同构），
# 避免测试发现顺序不同导致 bpy 模块被空桩污染。
bpy = types.ModuleType("bpy")
bpy.app = types.SimpleNamespace(version=(4, 2, 0))
bpy.context = types.SimpleNamespace(
    view_layer=types.SimpleNamespace(objects=types.SimpleNamespace(active=None)),
    preferences=types.SimpleNamespace(addons=[]))
bpy.data = types.SimpleNamespace(objects={}, materials={}, actions=[],
                                  lights=[], fields=[], node_groups={})


class _StubOps:
    def __getattr__(self, name):
        return _StubOps()

    def __call__(self, *args, **kwargs):
        return None


bpy.ops = _StubOps()
sys.modules["bpy"] = bpy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from blender_addon.handlers import addons  # noqa: E402
from blender_addon.handlers import addon_catalog  # noqa: E402


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


class TestAddonCatalog(unittest.TestCase):

    VALID_CAPS = {"modeling", "rigging", "animation", "effects",
                  "material", "render", "asset", "io", "other"}

    def test_catalog_entries_well_formed(self):
        self.assertGreaterEqual(len(addon_catalog.KNOWN_PLUGINS), 20)
        for entry in addon_catalog.KNOWN_PLUGINS:
            self.assertIn(entry["capability"], self.VALID_CAPS)
            self.assertTrue(entry["name"])
            self.assertTrue(entry["aliases"])
            self.assertTrue(entry["bridge_commands"])
            for cmd in entry["bridge_commands"]:
                self.assertIn("cmd", cmd)
                self.assertIn("note", cmd)

    def test_query_by_capability(self):
        rigging = addon_catalog.query_catalog(capability="rigging")
        names = {e["key"] for e in rigging}
        self.assertIn("auto_rig_pro", names)
        self.assertIn("faceit", names)

    def test_query_by_keyword(self):
        terrain = addon_catalog.query_catalog(keyword="地形")
        self.assertEqual(len(terrain), 1)
        self.assertEqual(terrain[0]["key"], "true_terrain")

    def test_catalog_match_rigging_intent(self):
        hits = addon_catalog.catalog_match("帮我自动绑定骨骼并分配权重")
        self.assertTrue(hits)
        self.assertEqual(hits[0]["key"], "auto_rig_pro")

    def test_catalog_match_empty_intent(self):
        self.assertEqual(addon_catalog.catalog_match(""), [])


if __name__ == "__main__":
    unittest.main()
