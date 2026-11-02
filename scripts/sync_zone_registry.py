#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync_zone_registry.py —— 免检区登记表机算字段刷新器（B16 补齐 · 工具固化）

背景（真实缺口，非假设）：
  此前刷新 references/inspection-zones.yaml 机算字段（key_count / keys_sha256 /
  leaf_unused / leaf_weak）的工具是**临时写在 /tmp 的一次性脚本**——
  跨会话即失 ⇒ 每逢「改 config 键值」都要重新手搓一遍，重写口径可能与守卫
  不同 ⇒ 曾出现「我自算的口径 ≠ 守卫口径」的假不一致（2026-11-01 实测）。
  本文件把刷新动作**固化进包内**，并**复用守卫的同一套口径函数**
  （ensure_settings.segments_digest / segment_digest_inputs / segment_key_count）
  ⇒ 口径必然一致，不可能再出现自算 ≠ 守卫。

安全边界（对齐个人文件操作纪律 + 包内写回纪律）：
  · **只覆盖四个机算字段**；人工字段（consumer / disposition / note / prefix /
    file / id）**一个字节都不动**——改完会打印人工字段漂移断言。
  · 默认**只读预览**（--dry-run 隐含），必须显式 --confirm 才写盘。
  · 幂等：已是实时值 ⇒ 报告「无需写入」，不产生 diff。

用法：
  python3 scripts/sync_zone_registry.py            # 预览（不写）
  python3 scripts/sync_zone_registry.py --confirm   # 写入
"""

import argparse
import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
REG = PKG / "references" / "inspection-zones.yaml"

#: 机算字段（唯一允许被覆盖的键）
MACHINE_FIELDS = ("key_count", "keys_sha256", "leaf_unused", "leaf_weak")


def _load_es():
    """加载 ensure_settings 模块（复用守卫的同一套口径函数）。"""
    spec = importlib.util.spec_from_file_location("es", HERE / "ensure_settings.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["es"] = m
    spec.loader.exec_module(m)
    return m


def _load_registry():
    import yaml
    return yaml.safe_load(REG.read_text(encoding="utf-8")) or {}


def _dump_registry(reg):
    import yaml
    REG.write_text(yaml.safe_dump(reg, allow_unicode=True, sort_keys=False),
                   encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="免检区登记表机算字段刷新器")
    ap.add_argument("--confirm", action="store_true",
                    help="确认写盘（缺省只预览）")
    args = ap.parse_args()

    es = _load_es()
    reg = _load_registry()
    segs = reg.get("segments") or []
    live = es.collect_block_segments(str(PKG))

    changed, ok, skipped = [], 0, []
    for s in segs:
        sid = s.get("id")
        prefix = s.get("prefix")
        file_name = s.get("file")
        seg_live = live.get(f"{file_name}#{prefix}") if file_name and prefix else None
        if seg_live is None:
            skipped.append(sid)
            continue
        scheme = s.get("digest_scheme") or es.DIGEST_SCHEME_INDEXED
        inputs = es.segment_digest_inputs(seg_live, scheme)
        live_sha = es.segments_digest(inputs, scheme=scheme)
        live_count = es.segment_key_count(inputs, scheme=scheme)
        old = {f: s.get(f) for f in MACHINE_FIELDS}
        # ⚠ leaf_unused / leaf_weak 的真值也来自实时段（守卫 R7/R8 比对它们）——
        #   此前沿用登记值 ⇒ 永远「一致」⇒ 守卫形同虚设（现修正）。
        new = {"key_count": live_count, "keys_sha256": live_sha,
               "leaf_unused": int(seg_live.get("leaf_unused", 0) or 0),
               "leaf_weak": int(seg_live.get("leaf_weak", 0) or 0)}
        if (old.get("keys_sha256") == live_sha
                and int(old.get("key_count", -1)) == int(live_count)
                and int(old.get("leaf_unused", -1)) == new["leaf_unused"]
                and int(old.get("leaf_weak", -1)) == new["leaf_weak"]):
            ok += 1
            continue
        for f in MACHINE_FIELDS:
            s[f] = new[f]
        changed.append((sid, old.get("keys_sha256"), live_sha,
                        old.get("key_count"), live_count))

    print(f"段总数 {len(segs)} | 已对齐 {ok} | 需刷新 {len(changed)} | "
          f"跳过(无实时对应) {len(skipped)}")
    if skipped:
        print(f"  跳过：{skipped}")
    for sid, o_sha, n_sha, o_cnt, n_cnt in changed:
        print(f"  ↻ {sid}: keys_sha256 {str(o_sha)[:12]} → {str(n_sha)[:12]} | "
              f"key_count {o_cnt} → {n_cnt}")

    if not changed:
        print("已是实时值，无需写入。")
        return 0

    if not args.confirm:
        print("\n（预览模式；加 --confirm 写盘）")
        return 0

    # 人工字段漂移断言：只应有 MACHINE_FIELDS 变动
    before = _load_registry()
    _dump_registry(reg)
    after = _load_registry()
    drift = []
    for b, a in zip(before.get("segments") or [], after.get("segments") or []):
        for k in set(b) | set(a):
            if k in MACHINE_FIELDS:
                continue
            if b.get(k) != a.get(k):
                drift.append((b.get("id"), k))
    if drift:
        print(f"⛔ 人工字段发生漂移（{drift}）——已回滚", file=sys.stderr)
        _dump_registry(before)
        return 3
    print(f"\n✓ 已写入 {REG}（人工字段零漂移）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
