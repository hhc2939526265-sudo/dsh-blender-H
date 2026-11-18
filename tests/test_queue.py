# -*- coding: utf-8 -*-
"""指令排队等待超时单元测试（无需 Blender）。"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "blender_addon"))

from core.queue import CommandQueue  # noqa: E402


class TestCommandQueue(unittest.TestCase):

    def test_stale_entry_dropped_after_timeout(self):
        q = CommandQueue(mode="serial", command_timeout=0.05)
        q.enqueue("c1", {"cmd_type": "modeling.create_cube"})
        time.sleep(0.08)
        items = q.drain()
        self.assertEqual(items, [])
        self.assertEqual(q.dropped_count(), 1)

    def test_fresh_entry_kept(self):
        q = CommandQueue(mode="serial", command_timeout=10.0)
        q.enqueue("c1", {"cmd_type": "modeling.create_cube"})
        items = q.drain()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0][0], "c1")

    def test_batch_limit_parallel(self):
        q = CommandQueue(mode="parallel", max_parallel=3, command_timeout=10.0)
        for i in range(5):
            q.enqueue(f"c{i}", {"cmd_type": "x"})
        items = q.drain()
        self.assertEqual(len(items), 3)
        self.assertEqual(q.pending_count(), 2)


if __name__ == "__main__":
    unittest.main()
