# -*- coding: utf-8 -*-
"""协议层单元测试（无需 Blender，标准库即可运行）。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "blender_addon"))

from core import protocol  # noqa: E402


class TestProtocol(unittest.TestCase):

    def test_new_command_envelope(self):
        env = protocol.newCommand("mesh.add_primitive", {"type": "cube"}) \
            if hasattr(protocol, "newCommand") else protocol.new_command("mesh.add_primitive", {"type": "cube"})
        for field in protocol.REQUIRED_FIELDS:
            self.assertIn(field, env)
        self.assertEqual(env["cmd_type"], "mesh.add_primitive")
        self.assertEqual(env["status"], protocol.STATUS_PENDING)
        self.assertEqual(env["error"], {"code": "", "message": "", "detail": ""})

    def test_validate_ok(self):
        env = protocol.new_command("mesh.bevel", {"object": "x"})
        self.assertEqual(protocol.validate_envelope(env), {})

    def test_validate_missing_field(self):
        bad = {"cmd_id": "1", "cmd_type": "x"}
        err = protocol.validate_envelope(bad)
        self.assertEqual(err["code"], "E_PROTOCOL")

    def test_validate_bad_status(self):
        env = protocol.new_command("x")
        env["status"] = "NOT_A_STATUS"
        err = protocol.validate_envelope(env)
        self.assertEqual(err["code"], "E_PROTOCOL")

    def test_make_result(self):
        receipt = protocol.make_result("cid", "x", protocol.STATUS_SUCCESS, {"a": 1})
        self.assertEqual(receipt["cmd_id"], "cid")
        self.assertEqual(receipt["status"], protocol.STATUS_SUCCESS)
        self.assertEqual(receipt["result"], {"a": 1})


if __name__ == "__main__":
    unittest.main()
