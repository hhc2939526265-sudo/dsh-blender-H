# -*- coding: utf-8 -*-
"""处理器层参数守卫与安全策略测试（注入空 bpy 桩，无需真机 Blender）。"""

import sys
import os
import types
import unittest

# 未安装 Blender 的环境下注入最小 bpy 桩：仅满足模块导入与活动对象解析
bpy = types.ModuleType("bpy")
bpy.app = types.SimpleNamespace(version=(4, 2, 0))
bpy.context = types.SimpleNamespace(
    view_layer=types.SimpleNamespace(objects=types.SimpleNamespace(active=None)))
bpy.data = types.SimpleNamespace(objects={}, materials={}, actions=[],
                                  lights=[], fields=[])


class _StubOps:
    """递归算子桩：任意命名空间下的算子均解析为可调用空操作。"""

    def __getattr__(self, name):
        return _StubOps()

    def __call__(self, *args, **kwargs):
        return None


bpy.ops = _StubOps()
sys.modules["bpy"] = bpy

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from blender_addon.handlers import (_helpers, modeling, animation, effects,
                                     material, addons)  # noqa: E402
from blender_addon.core import transfer, dispatcher  # noqa: E402
from blender_addon.utils import paths  # noqa: E402


class _Obj:
    """模拟 Blender 对象的最小桩。"""

    def __init__(self, name="Obj", obj_type="MESH"):
        self.name = name
        self.type = obj_type
        self.location = [0.0, 0.0, 0.0]
        self.rotation_euler = [0.0, 0.0, 0.0]
        self.scale = [1.0, 1.0, 1.0]
        self.data = types.SimpleNamespace(materials=[])


class _MeshObj(_Obj):
    """带网格边集合的桩对象。"""

    def __init__(self, name="Cube"):
        super().__init__(name, "MESH")
        self.data.edges = []


class _ArmatureStub:
    """最小骨架桩：pose.bones 字典 + 约束列表桩。"""

    def __init__(self, name="Rig"):
        self.name = name
        self.type = "ARMATURE"
        bone = types.SimpleNamespace(
            constraints=[], rotation_euler=[0.0, 0.0, 0.0],
            location=[0.0, 0.0, 0.0])
        self.pose = types.SimpleNamespace(bones={"hips": bone})


class TestActiveRef(unittest.TestCase):

    def test_active_resolves_to_context_active(self):
        obj = _Obj("ActiveMesh")
        bpy.context.view_layer.objects.active = obj
        self.assertIs(_helpers.require_object("active"), obj)
        self.assertIs(_helpers.require_object(None), obj)
        self.assertIs(_helpers.get_object("active"), obj)

    def test_active_without_selection_raises(self):
        bpy.context.view_layer.objects.active = None
        with self.assertRaises(KeyError):
            _helpers.require_object("active")

    def tearDown(self):
        bpy.context.view_layer.objects.active = None

    def test_named_missing_raises(self):
        with self.assertRaises(KeyError):
            _helpers.require_object("no_such_object")


class TestModelingGuards(unittest.TestCase):

    def test_curve_requires_two_points(self):
        with self.assertRaises(ValueError):
            modeling.curve({"points": [[0, 0, 0]]}, None)

    def test_curve_requires_three_components(self):
        with self.assertRaises(ValueError):
            modeling.curve({"points": [[0, 0], [1, 1]]}, None)

    def test_curve_empty_points_rejected(self):
        with self.assertRaises(ValueError):
            modeling.curve({"points": []}, None)


class TestAnimationGuards(unittest.TestCase):

    def setUp(self):
        self.obj = _Obj()
        bpy.context.view_layer.objects.active = self.obj

    def test_keyframe_bad_mode_rejected(self):
        with self.assertRaises(ValueError):
            animation.keyframe({"object": "active", "mode": "transform",
                                "frames": [[0, [0, 0, 0]]]}, None)

    def test_keyframe_values_length_mismatch(self):
        with self.assertRaises(ValueError):
            animation.keyframe({"object": "active", "mode": "location",
                                "frames": [[0, [0, 0]]]}, None)

    def test_loop_cycle_bad_type_rejected(self):
        with self.assertRaises(ValueError):
            animation.loop_cycle({"object": "active", "cycle": "fly"}, None)


class TestEffectsGuards(unittest.TestCase):

    def setUp(self):
        self.obj = _Obj()
        bpy.context.view_layer.objects.active = self.obj

    def test_deform_short_timing_rejected(self):
        with self.assertRaises(ValueError):
            effects.deform({"object": "active", "deform": {"timing": [0]}}, None)

    def test_deform_inverted_timing_rejected(self):
        with self.assertRaises(ValueError):
            effects.deform({"object": "active", "deform": {"timing": [24, 0]}}, None)


class TestPaths(unittest.TestCase):

    def test_safe_name_strips_traversal(self):
        self.assertEqual(paths.safe_name("../../etc/passwd"), "passwd")
        with self.assertRaises(ValueError):
            paths.safe_name("../")

    def test_is_within(self):
        base = "/home/user/DSH_Bridge/transfer"
        self.assertTrue(paths.is_within(base, os.path.join(base, "a.png")))
        self.assertFalse(paths.is_within(base, "/etc/passwd"))

    def test_require_within_raises(self):
        with self.assertRaises(PermissionError):
            paths.require_within("/home/user/DSH_Bridge/transfer", "/etc/passwd")


class TestTransferGuards(unittest.TestCase):

    def setUp(self):
        self.mgr = transfer.TransferManager(save_dir=paths.subdir("temp"),
                                            chunk_size=64 * 1024,
                                            max_total_bytes=1024 * 1024)

    def test_begin_rejects_zero_chunk_count(self):
        res = self.mgr.begin({"file_id": "f1", "chunk_count": 0, "total_size": 10})
        self.assertFalse(res["ok"])

    def test_begin_rejects_oversize(self):
        res = self.mgr.begin({"file_id": "f1", "chunk_count": 2,
                              "total_size": 1024 * 1024 * 10})
        self.assertFalse(res["ok"])

    def test_chunk_index_out_of_range(self):
        self.mgr.begin({"file_id": "f2", "chunk_count": 2, "total_size": 10})
        res = self.mgr.add_chunk({"file_id": "f2", "index": 5, "data": ""})
        self.assertFalse(res["ok"])

    def test_is_complete_requires_index_set(self):
        sess = transfer.TransferSession("f3", "a.bin", 10, "d41d8cd98f00b204e9800998ecf8427e",
                                        3, paths.subdir("temp"))
        sess.chunks[0] = b"a"
        sess.chunks[2] = b"c"
        self.assertFalse(sess.is_complete())


class _Ctx:
    def __init__(self, config):
        self.config = config
        self.log = lambda *a, **k: None


class TestAddonOperatorPolicy(unittest.TestCase):

    def test_denylist_blocks_dangerous_operator(self):
        ctx = _Ctx({"allow_addon_invoke": True,
                    "addon_operator_allowlist": [],
                    "addon_operator_denylist": ["wm.open_mainfile", "script."]})
        with self.assertRaises(PermissionError):
            addons.invoke_operator({"operator": "wm.open_mainfile", "params": {}}, ctx)

    def test_allowlist_rejects_unprefixed_operator(self):
        ctx = _Ctx({"allow_addon_invoke": True,
                    "addon_operator_allowlist": ["mesh"],
                    "addon_operator_denylist": []})
        with self.assertRaises(PermissionError):
            addons.invoke_operator({"operator": "object.shade_smooth", "params": {}}, ctx)

    def test_disabled_invoke_rejected(self):
        ctx = _Ctx({"allow_addon_invoke": False,
                    "addon_operator_allowlist": [], "addon_operator_denylist": []})
        with self.assertRaises(PermissionError):
            addons.invoke_operator({"operator": "mesh.primitive_cube_add", "params": {}}, ctx)


class TestNewModelingGuards(unittest.TestCase):

    def setUp(self):
        self.obj = _MeshObj()
        bpy.context.view_layer.objects.active = self.obj

    def test_separate_bad_type_rejected(self):
        with self.assertRaises(ValueError):
            modeling.separate({"object": "active", "type": "SPLIT"}, None)

    def test_crease_non_mesh_rejected(self):
        empty = _Obj("Empty", "EMPTY")
        bpy.context.view_layer.objects.active = empty
        with self.assertRaises(ValueError):
            modeling.crease({"object": "active"}, None)


class TestNewEffectGuards(unittest.TestCase):

    def setUp(self):
        self.obj = _Obj()
        bpy.context.view_layer.objects.active = self.obj

    def test_light_bad_type_rejected(self):
        with self.assertRaises(ValueError):
            effects.light({"type": "LASER"}, None)

    def test_force_field_bad_kind_rejected(self):
        with self.assertRaises(ValueError):
            effects.force_field({"object": "active", "kind": "ANTIGRAVITY"}, None)


class TestMaterialGuards(unittest.TestCase):

    def setUp(self):
        self.obj = _Obj()
        bpy.context.view_layer.objects.active = self.obj

    def test_assign_missing_material_rejected(self):
        with self.assertRaises(KeyError):
            material.assign({"object": "active", "material_name": "NoSuch"}, None)


class TestRegistry(unittest.TestCase):

    def test_new_commands_registered_and_counts(self):
        d = dispatcher.Dispatcher(None, None, {})
        modeling.register(d)
        animation.register(d)
        material.register(d)
        effects.register(d)
        names = set(d.available_commands())
        expected = [
            "mesh.duplicate", "mesh.join", "mesh.separate", "mesh.screw",
            "mesh.wireframe", "mesh.displace", "mesh.edge_split",
            "mesh.shrinkwrap", "mesh.crease",
            "anim.clear", "anim.ik", "anim.copy_transform",
            "anim.action_list", "anim.parent_set",
            "anim.bone_keyframe", "anim.pose", "anim.follow_target",
            "anim.action_mix",
            "material.assign", "material.clear", "material.list",
            "material.emission",
            "effect.force_field", "effect.light", "effect.world",
            "effect.hair", "effect.motion_blur",
            "effect.trail", "effect.shockwave", "effect.shield",
            "effect.lightning", "effect.aura", "effect.debris",
            "effect.spark", "effect.camera_shake",
        ]
        for cmd in expected:
            self.assertIn(cmd, names)
        self.assertEqual(len([n for n in names if n.startswith("mesh.")]), 35)
        self.assertEqual(len([n for n in names if n.startswith("anim.")]), 17)
        self.assertEqual(len([n for n in names if n.startswith("material.")]), 10)
        self.assertEqual(len([n for n in names if n.startswith("effect.")]), 18)


class TestFightAnimationGuards(unittest.TestCase):

    def setUp(self):
        self.obj = _Obj()
        bpy.context.view_layer.objects.active = self.obj

    def test_pose_empty_rejected(self):
        with self.assertRaises(ValueError):
            animation.pose({"object": "active", "poses": {}}, None)

    def test_follow_bad_constraint_rejected(self):
        with self.assertRaises(ValueError):
            animation.follow_target({"object": "active", "target": "active",
                                     "constraint": "TELEPORT"}, None)

    def test_action_mix_empty_layers_rejected(self):
        with self.assertRaises(ValueError):
            animation.action_mix({"object": "active", "layers": []}, None)

    def test_bone_keyframe_missing_bone(self):
        arm = _ArmatureStub()
        bpy.context.view_layer.objects.active = arm
        with self.assertRaises(KeyError):
            animation.bone_keyframe({"object": "active", "bone": "no_bone",
                                     "rotation": [0, 0, 0]}, None)

    def test_lightning_missing_start_rejected(self):
        with self.assertRaises(ValueError):
            effects.lightning({"end": [1, 1, 1]}, None)

    def test_shockwave_inverted_timing_rejected(self):
        with self.assertRaises(ValueError):
            effects.shockwave({"object": "active",
                               "shockwave": {"timing": [24, 0]}}, None)


if __name__ == "__main__":
    unittest.main()
