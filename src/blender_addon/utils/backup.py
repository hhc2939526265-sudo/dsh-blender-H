# -*- coding: utf-8 -*-
"""
场景备份与一键回滚（Blender 端）。

备份策略（双保险）：
1. Blend 文件快照：将当前工程另存一份到备份槽位（copy 模式，不改变当前文件）
2. JSON 清单：记录对象名、变换、可见性，用于轻量回滚与对象增删还原

槽位采用环形覆盖，超出上限后最早的备份被替换。
"""

from __future__ import annotations

import os
import json
import time
import bpy
from typing import Any, Dict, List, Optional


class BackupManager:
    """场景备份槽位管理器。"""

    def __init__(self, backup_dir: str, max_slots: int = 5):
        self.backup_dir = backup_dir
        self.max_slots = max_slots
        self._slots: List[Dict[str, Any]] = []
        os.makedirs(backup_dir, exist_ok=True)
        # 重启 Blender 后内存槽位丢失，按备份目录回补历史记录
        self._rescan_slots()

    # ------------------------------------------------------------- 目录回补
    def _rescan_slots(self) -> None:
        """扫描备份目录，把历史 JSON 清单回补到内存槽位列表。"""
        try:
            names = sorted(os.listdir(self.backup_dir))
        except OSError:
            return
        records: List[Dict[str, Any]] = []
        for name in names:
            if not name.startswith("backup_") or not name.endswith(".json"):
                continue
            json_path = os.path.join(self.backup_dir, name)
            # 文件名约定：backup_<slot>_<timestamp>.json
            parts = name[len("backup_"):-len(".json")].split("_", 1)
            try:
                slot_index = int(parts[0])
                manifest: Dict[str, Any] = {}
                with open(json_path, "r", encoding="utf-8") as fh:
                    manifest = json.load(fh)
            except (OSError, ValueError, IndexError):
                continue
            blend_path = json_path[:-len(".json")] + ".blend"
            records.append({
                "slot": slot_index,
                "label": str(manifest.get("label", "restored")),
                "timestamp": str(manifest.get("timestamp", "")),
                "blend_path": blend_path if os.path.isfile(blend_path) else "",
                "json_path": json_path,
                "object_count": len(manifest.get("objects", [])),
            })
        records.sort(key=lambda r: r["timestamp"])
        self._slots = records[-self.max_slots:]

    # ------------------------------------------------------------- 快照
    def snapshot(self, label: str = "auto") -> Dict[str, Any]:
        """
        创建一次场景备份。

        :return: 备份元信息（slot 索引、路径、对象清单、时间戳）
        """
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        slot_index = len(self._slots) % self.max_slots

        # 对象清单（JSON 快照）
        manifest = {"label": label, "timestamp": timestamp, "objects": []}
        for obj in bpy.data.objects:
            manifest["objects"].append({
                "name": obj.name,
                "location": list(obj.location),
                "rotation_euler": list(obj.rotation_euler),
                "scale": list(obj.scale),
                "visible": not obj.hide_viewport,
                "type": obj.type,
            })

        blend_path = os.path.join(self.backup_dir, f"backup_{slot_index}_{timestamp}.blend")
        json_path = os.path.join(self.backup_dir, f"backup_{slot_index}_{timestamp}.json")

        # 1) Blend 文件副本（copy=True 不切换当前工程文件）
        blend_ok = False
        try:
            bpy.ops.wm.save_as_mainfile(filepath=blend_path, copy=True)
            blend_ok = os.path.isfile(blend_path)
        except (RuntimeError, TypeError, OSError):
            blend_ok = False

        # 2) JSON 清单
        with open(json_path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh, ensure_ascii=False, indent=2)

        record = {"slot": slot_index, "label": label, "timestamp": timestamp,
                  "blend_path": blend_path if blend_ok else "",
                  "json_path": json_path, "object_count": len(manifest["objects"])}
        self._slots.append(record)
        if len(self._slots) > self.max_slots:
            self._slots.pop(0)
        return record

    # ------------------------------------------------------------- 回滚
    def rollback(self, slot: Optional[int] = None) -> Dict[str, Any]:
        """
        回滚到指定备份槽位；默认回滚最近一次。

        优先恢复 Blend 快照；不可用时按 JSON 清单还原变换并移除新增对象。
        """
        if not self._slots:
            return {"ok": False, "error": "暂无可用备份"}

        if slot is not None and not (0 <= int(slot) < len(self._slots)):
            return {"ok": False,
                    "error": f"备份槽位越界: {slot}（当前共 {len(self._slots)} 个槽位）"}
        record = self._slots[slot] if slot is not None else self._slots[-1]

        # 路径回补（重启后槽位记录可能丢失，按目录匹配）
        if record.get("blend_path") and os.path.isfile(record["blend_path"]):
            try:
                bpy.ops.wm.open_mainfile(filepath=record["blend_path"])
                return {"ok": True, "mode": "blend", "record": record}
            except (RuntimeError, OSError):
                pass

        # JSON 清单回滚
        if os.path.isfile(record["json_path"]):
            with open(record["json_path"], "r", encoding="utf-8") as fh:
                manifest = json.load(fh)
            self._restore_from_manifest(manifest)
            return {"ok": True, "mode": "manifest", "record": record}

        return {"ok": False, "error": "备份文件已丢失"}

    def _restore_from_manifest(self, manifest: Dict[str, Any]) -> None:
        """按清单还原已有对象变换，并删除备份后新增的对象。"""
        known = {o["name"] for o in manifest["objects"]}
        # 还原变换
        for entry in manifest["objects"]:
            obj = bpy.data.objects.get(entry["name"])
            if obj is None:
                continue
            obj.location = entry["location"]
            obj.rotation_euler = entry["rotation_euler"]
            obj.scale = entry["scale"]
            obj.hide_viewport = not entry["visible"]
        # 移除新增对象
        for obj in list(bpy.data.objects):
            if obj.name not in known:
                bpy.data.objects.remove(obj, do_unlink=True)

    def list_slots(self) -> List[Dict[str, Any]]:
        return list(self._slots)
