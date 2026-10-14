#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
snapshot.py — 课件快照库（v3.2.0-batch2）

> 适用场景：WF-2R 闸 4 写回前自动打点；D12（备份膨胀）治理。
> 目标：以"快照库 + K=3 + 里程碑 + 500MB LRU"替代"每次修改都备份"。
> 触发：harness.py cmd_gate 写回前自动调 `snapshot snap`（sha256 去重，内容未变不产生文件）。

存储结构：
  <workspace>/.snapshots/<deck_basename>/
    <sha8>_<ts>.pptx              ← 快照文件
    manifest.json                 ← 索引（去重+LRU 治理依据）

CLI：
  python3 snapshot.py snap <deck.pptx> [--workspace <ws>] [--tag <name>]
  python3 snapshot.py list <deck.pptx> [--workspace <ws>]
  python3 snapshot.py rollback <deck.pptx> <sha8_or_ts_tag> [--workspace <ws>]
  python3 snapshot.py gc [--workspace <ws>] [--max 500MB] [--keep 3]
  python3 snapshot.py status <deck.pptx> [--workspace <ws>]

退出码（与 harness.py 一致）：0/1/2/3/4
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("snapshot")

SCHEMA_VERSION = 1
DEFAULT_MAX_SIZE_MB = 500
DEFAULT_KEEP = 3
MAX_MB_BYTES = DEFAULT_MAX_SIZE_MB * 1024 * 1024


# ============== 数据类 ==============
@dataclass
class SnapshotEntry:
    sha8: str
    ts: str
    size_bytes: int
    trigger: str        # auto_pre_writeback / milestone / manual
    gate_exit: int = 0  # 触发时 gate 的退出码
    tag: str = ""
    kept: bool = True


# ============== 工具 ==============
def _sha256_file(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha8(sha256: str) -> str:
    return sha256[:8]


# ============== 存储 ==============
class SnapshotStore:
    """单 deck 的快照存储：打/查/回滚/清理。"""

    def __init__(self, deck: Path, workspace: Path,
                 max_size_mb: int = DEFAULT_MAX_SIZE_MB, keep: int = DEFAULT_KEEP):
        self.deck = Path(deck).resolve()
        self.workspace = Path(workspace).resolve()
        self.basename = self.deck.name
        self.store_dir = self.workspace / ".snapshots" / self.basename
        self.manifest_path = self.store_dir / "manifest.json"
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.keep = keep  # K=3
        self.manifest = self._load_manifest()

    def _load_manifest(self) -> dict:
        if not self.manifest_path.exists():
            return {
                "schema_version": SCHEMA_VERSION,
                "deck_basename": self.basename,
                "snapshots": [],
                "totals": {"count": 0, "size_bytes": 0, "max_size_mb": self.max_size_bytes // (1024*1024), "k": self.keep},
            }
        try:
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("manifest 损坏，重建: %s", e)
            return {
                "schema_version": SCHEMA_VERSION,
                "deck_basename": self.basename,
                "snapshots": [],
                "totals": {"count": 0, "size_bytes": 0, "max_size_mb": self.max_size_bytes // (1024*1024), "k": self.keep},
            }

    def _save_manifest(self):
        self.store_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(self.manifest, ensure_ascii=False, indent=2, sort_keys=False),
            encoding="utf-8",
        )

    def _refresh_totals(self):
        snaps = self.manifest["snapshots"]
        kept = [s for s in snaps if s.get("kept", True)]
        self.manifest["totals"] = {
            "count": len(kept),
            "size_bytes": sum(s["size_bytes"] for s in kept),
            "max_size_mb": self.max_size_bytes // (1024*1024),
            "k": self.keep,
        }

    # ---------- 打点 ----------
    def snap(self, trigger: str = "auto_pre_writeback", gate_exit: int = 0, tag: str = "") -> Optional[str]:
        if not self.deck.exists():
            log.error("deck 不存在: %s", self.deck)
            return None
        # 算 sha256
        sha256 = _sha256_file(self.deck)
        sha8 = _sha8(sha256)
        # 去重：若已存在同 sha8 快照
        existing = [s for s in self.manifest["snapshots"] if s["sha8"] == sha8]
        if existing:
            log.info("sha8=%s 已存在快照，跳过", sha8)
            return sha8
        # 写新快照
        self.store_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        snap_name = f"{sha8}_{ts}.pptx"
        snap_path = self.store_dir / snap_name
        size = self.deck.stat().st_size
        # 用 shutil.copy 防 partial write
        shutil.copy2(self.deck, snap_path)
        entry = {
            "sha8": sha8,
            "ts": datetime.now().isoformat(timespec="seconds"),
            "size_bytes": size,
            "trigger": trigger,
            "gate_exit": gate_exit,
            "tag": tag,
            "kept": True,
        }
        self.manifest["snapshots"].append(entry)
        self._refresh_totals()
        self._save_manifest()
        log.info("已打点: %s (%d MB)", snap_name, size // (1024*1024))
        # 打点后立即 GC
        self.gc()
        return sha8

    # ---------- 列出 ----------
    def list_snapshots(self) -> list[dict]:
        return self.manifest.get("snapshots", [])

    # ---------- 回滚 ----------
    def rollback(self, target: str) -> bool:
        """target 可以是 sha8（8 字符）或 ts 标签。"""
        snaps = self.manifest["snapshots"]
        # 找匹配
        match = None
        for s in snaps:
            if s["sha8"] == target or target in s.get("ts", "") or target == s.get("tag", ""):
                match = s
                break
        if not match:
            log.error("未找到快照: %s", target)
            return False
        # 找对应文件
        snap_files = list(self.store_dir.glob(f"{match['sha8']}_*.pptx"))
        if not snap_files:
            log.error("快照文件不存在: %s", match["sha8"])
            return False
        snap_path = snap_files[0]
        # 先把当前活跃版打成新快照（防回滚丢失）
        if self.deck.exists():
            log.info("回滚前先打点当前活跃版")
            self.snap(trigger="rollback_snapshot")
        # 用临时文件 + os.replace 防 partial write
        with tempfile.NamedTemporaryFile(delete=False, dir=str(self.deck.parent), suffix=".tmp") as tmp:
            shutil.copy2(snap_path, tmp.name)
            tmp_path = tmp.name
        try:
            os.replace(tmp_path, self.deck)
        except Exception as e:
            log.error("回滚失败: %s", e)
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            return False
        log.info("已回滚到 %s", match["sha8"])
        return True

    # ---------- 清理 ----------
    def gc(self) -> int:
        """LRU + K 保留：淘汰非里程碑 + 非最近 K 个。返回淘汰条数。"""
        snaps = self.manifest["snapshots"]
        if not snaps:
            return 0
        # 1) 先按 K 保留最近 + 全部里程碑
        # 排序：按 ts 倒序
        sorted_snaps = sorted(snaps, key=lambda s: s["ts"], reverse=True)
        keep_set = set()
        for i, s in enumerate(sorted_snaps):
            if i < self.keep or s.get("tag"):
                keep_set.add(s["sha8"])
        # 2) 再按 size 超容
        kept_snaps = [s for s in snaps if s["sha8"] in keep_set]
        total_size = sum(s["size_bytes"] for s in kept_snaps)
        evicted = 0
        if total_size > self.max_size_bytes:
            # 按 ts 升序淘汰最早的非里程碑
            for s in sorted(sorted_snaps, key=lambda s: s["ts"]):
                if s["sha8"] in keep_set and not s.get("tag"):
                    keep_set.discard(s["sha8"])
                    s["kept"] = False
                    evicted += 1
                    # 删文件
                    for f in self.store_dir.glob(f"{s['sha8']}_*.pptx"):
                        try:
                            f.unlink()
                        except OSError:
                            pass
                    # 重算
                    kept_snaps = [x for x in snaps if x["sha8"] in keep_set]
                    total_size = sum(x["size_bytes"] for x in kept_snaps)
                    if total_size <= self.max_size_bytes:
                        break
        # 3) 更新 manifest
        for s in snaps:
            s["kept"] = s["sha8"] in keep_set
        self._refresh_totals()
        self._save_manifest()
        if evicted:
            log.info("GC 淘汰 %d 个快照（超容 %d MB）", evicted, self.max_size_bytes // (1024*1024))
        return evicted

    # ---------- 状态 ----------
    def status(self) -> str:
        self._refresh_totals()
        return json.dumps(self.manifest, ensure_ascii=False, indent=2)


# ============== CLI ==============
def main():
    ap = argparse.ArgumentParser(description="课件快照库（v3.2.0-batch2）")
    ap.add_argument("subcommand", choices=["snap", "list", "rollback", "gc", "status"],
                    help="子命令")
    ap.add_argument("deck", nargs="?", help="课件 .pptx 路径（gc 子命令可选）")
    ap.add_argument("target", nargs="?", help="rollback 时的 sha8 / ts / tag")
    ap.add_argument("--workspace", default=".", help="工作空间根（默认当前目录）")
    ap.add_argument("--max", type=int, default=DEFAULT_MAX_SIZE_MB, help=f"最大容量 MB（默认 {DEFAULT_MAX_SIZE_MB}）")
    ap.add_argument("--keep", type=int, default=DEFAULT_KEEP, help=f"K 保留数（默认 {DEFAULT_KEEP}）")
    ap.add_argument("--tag", default="", help="打点标签（milestone=v3.2.0-batch2）")
    ap.add_argument("--trigger", default="manual", help="触发类型（auto_pre_writeback / milestone / manual）")
    ap.add_argument("--gate-exit", type=int, default=0, help="触发时 gate 退出码")
    args = ap.parse_args()

    workspace = Path(args.workspace).resolve()

    if args.subcommand == "gc":
        # 全局 GC：遍历 workspace/.snapshots/ 下所有 deck
        snap_root = workspace / ".snapshots"
        if not snap_root.exists():
            print("无快照库")
            return 0
        total = 0
        for deck_dir in snap_root.iterdir():
            if not deck_dir.is_dir():
                continue
            # 找 deck 真实路径（从 manifest 找）
            manifest = deck_dir / "manifest.json"
            if not manifest.exists():
                continue
            m = json.loads(manifest.read_text(encoding="utf-8"))
            # GC 逻辑直接基于 manifest
            snaps = m.get("snapshots", [])
            sorted_snaps = sorted(snaps, key=lambda s: s["ts"], reverse=True)
            keep_n = args.keep
            keep_set = set()
            for i, s in enumerate(sorted_snaps):
                if i < keep_n or s.get("tag"):
                    keep_set.add(s["sha8"])
            for s in snaps:
                s["kept"] = s["sha8"] in keep_set
            evicted = 0
            for s in snaps:
                if not s["kept"]:
                    for f in deck_dir.glob(f"{s['sha8']}_*.pptx"):
                        try:
                            f.unlink()
                            evicted += 1
                        except OSError:
                            pass
            kept = [s for s in snaps if s["kept"]]
            m["snapshots"] = snaps
            m["totals"] = {
                "count": len(kept),
                "size_bytes": sum(s["size_bytes"] for s in kept),
                "max_size_mb": args.max,
                "k": args.keep,
            }
            manifest.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")
            total += evicted
        print(f"GC 完成：淘汰 {total} 个快照")
        return 0

    if not args.deck:
        print("需要 deck 路径", file=sys.stderr)
        return 1

    deck = Path(args.deck).resolve()
    if not deck.exists():
        print(f"deck 不存在: {deck}", file=sys.stderr)
        return 3

    store = SnapshotStore(deck, workspace, max_size_mb=args.max, keep=args.keep)

    if args.subcommand == "snap":
        sha8 = store.snap(trigger=args.trigger, gate_exit=args.gate_exit, tag=args.tag)
        if sha8:
            print(f"✓ 打点成功: {sha8}")
            return 0
        return 1
    elif args.subcommand == "list":
        snaps = store.list_snapshots()
        if not snaps:
            print("无快照")
            return 0
        print(f"== {len(snaps)} 个快照 ==")
        for s in snaps:
            tag = f" [tag={s['tag']}]" if s.get("tag") else ""
            kept = "" if s.get("kept", True) else " [EVICTED]"
            print(f"  {s['sha8']} {s['ts']} {s['size_bytes']//1024//1024}MB trigger={s['trigger']}{tag}{kept}")
        return 0
    elif args.subcommand == "rollback":
        if not args.target:
            print("rollback 需要 target (sha8 / ts / tag)", file=sys.stderr)
            return 1
        ok = store.rollback(args.target)
        return 0 if ok else 1
    elif args.subcommand == "status":
        print(store.status())
        return 0
    return 0


if __name__ == "__main__":
    main()
