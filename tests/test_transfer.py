# -*- coding: utf-8 -*-
"""分片传输与 MD5 校验单元测试（无需 Blender）。"""

import base64
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "blender_addon"))

from core.transfer import TransferManager, md5_of_bytes  # noqa: E402


class TestTransfer(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.mgr = TransferManager(save_dir=self.tmp, chunk_size=1024,
                                   verify_md5=True, resume_enabled=True)

    def _upload(self, data: bytes, file_id: str = "f1"):
        md5 = md5_of_bytes(data)
        chunk_count = max(1, (len(data) + 1023) // 1024)
        self.mgr.begin({"file_id": file_id, "filename": "bin.dat",
                        "total_size": len(data), "md5": md5,
                        "chunk_count": chunk_count})
        for i in range(chunk_count):
            block = data[i * 1024:(i + 1) * 1024]
            self.mgr.add_chunk({"file_id": file_id, "index": i,
                                "data": base64.b64encode(block).decode()})
        return self.mgr.finish({"file_id": file_id}), md5

    def test_roundtrip_md5_ok(self):
        data = os.urandom(4096)
        res, md5 = self._upload(data)
        self.assertTrue(res["ok"])
        self.assertEqual(res["md5"], md5)
        with open(res["path"], "rb") as fh:
            self.assertEqual(fh.read(), data)

    def test_resume_missing_indexes(self):
        data = os.urandom(3000)
        md5 = md5_of_bytes(data)
        begin = self.mgr.begin({"file_id": "f2", "filename": "b.dat",
                                "total_size": len(data), "md5": md5, "chunk_count": 3})
        self.assertEqual(begin["missing"], [0, 1, 2])
        # 只发第 0 片
        self.mgr.add_chunk({"file_id": "f2", "index": 0,
                            "data": base64.b64encode(data[:1024]).decode()})
        resumed = self.mgr.begin({"file_id": "f2", "filename": "b.dat",
                                  "total_size": len(data), "md5": md5, "chunk_count": 3})
        self.assertEqual(resumed["missing"], [1, 2])

    def test_md5_mismatch_rejected(self):
        data = os.urandom(2048)
        self.mgr.begin({"file_id": "f3", "filename": "b.dat",
                        "total_size": len(data), "md5": "0" * 32, "chunk_count": 2})
        for i in range(2):
            block = data[i * 1024:(i + 1) * 1024]
            self.mgr.add_chunk({"file_id": "f3", "index": i,
                                "data": base64.b64encode(block).decode()})
        res = self.mgr.finish({"file_id": "f3"})
        self.assertFalse(res["ok"])
        self.assertEqual(res["error"], "MD5 校验失败")

    def test_split_file(self):
        path = os.path.join(self.tmp, "src.bin")
        data = os.urandom(5000)
        with open(path, "wb") as fh:
            fh.write(data)
        packed = self.mgr.split_file(path)
        self.assertEqual(packed["chunk_count"], 5)
        self.assertEqual(packed["md5"], md5_of_bytes(data))


if __name__ == "__main__":
    unittest.main()
