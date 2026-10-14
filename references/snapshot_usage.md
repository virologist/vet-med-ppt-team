# snapshot.py 使用手册（v3.2.0-batch2）

> WF-2R 闸 4 写回前自动打点；D12（备份膨胀）治理。版本：`snapshot/1.0.0`。
> 适用读者：主理人（编排）、郅作基（台账与门禁集成）、开发者（维护）。

---

## 1. 这是干什么的

以"快照库 + K=3 + 里程碑 + 500MB LRU"替代"每次修改都备份"。**sha256 去重**——内容未变不产生新文件。**保留** = 最近 K=3 + 全部里程碑。**清理** = 超 500MB 走 LRU 淘汰，淘汰记录留 manifest。

**不做啥**：不修文件（只快照 + 回滚）；不动 original 备份（属另一回事）；不管 scratch（那是 snapshot.py 之外的事）。

---

## 2. 快速上手

```bash
# 打点（最常用）
python3 scripts/snapshot.py snap /path/to/课件.pptx --workspace .

# 列出快照
python3 scripts/snapshot.py list /path/to/课件.pptx --workspace .

# 里程碑打点
python3 scripts/snapshot.py snap /path/to/课件.pptx --tag "v3.2.0-batch2-交付" --trigger milestone

# 回滚（指定 sha8 前 8 字符）
python3 scripts/snapshot.py rollback /path/to/课件.pptx a1b2c3d4

# 全局 GC（遍历 <workspace>/.snapshots/ 下所有 deck）
python3 scripts/snapshot.py gc --workspace . --keep 3 --max 500

# 状态查询
python3 scripts/snapshot.py status /path/to/课件.pptx --workspace .
```

---

## 3. 存储结构

```
<workspace>/.snapshots/<deck_basename>/
├── a1b2c3d4_20261014_113000.pptx    ← 快照文件（sha8_时间戳）
├── f9e8d7c6_20261014_114500.pptx    ← 里程碑快照（带 tag 不被淘汰）
└── manifest.json                    ← 索引（含 sha8 / ts / size / trigger / tag / kept）
```

manifest schema：
```json
{
  "schema_version": 1,
  "deck_basename": "禽流感鉴别诊疗要点.pptx",
  "snapshots": [
    {
      "sha8": "a1b2c3d4",
      "ts": "2026-10-14T11:30:00",
      "size_bytes": 36743080,
      "trigger": "auto_pre_writeback",
      "gate_exit": 0,
      "tag": "",
      "kept": true
    }
  ],
  "totals": {"count": 1, "size_bytes": 36743080, "max_size_mb": 500, "k": 3}
}
```

---

## 4. 字段表

| 字段 | 含义 |
|---|---|
| `schema_version` | 1（机器校验用） |
| `deck_basename` | 课件文件名（不含路径） |
| `snapshots[].sha8` | sha256 前 8 字符（去重主键） |
| `snapshots[].ts` | ISO8601 时间戳 |
| `snapshots[].size_bytes` | 快照文件字节数 |
| `snapshots[].trigger` | 触发类型：`auto_pre_writeback` / `milestone` / `manual` / `rollback_snapshot` |
| `snapshots[].gate_exit` | 触发时 gate 的退出码（v3.0.0 语义 0/1/2/3/4） |
| `snapshots[].tag` | 里程碑标签（如 `v3.2.0-batch2-交付`）；非空时**永不被淘汰** |
| `snapshots[].kept` | 是否仍在保留集中 |
| `totals` | 当前保留集统计 |

---

## 5. 退出码语义

| 码 | 含义 | 应对 |
|---|---|---|
| 0 | 成功 | 直接消费 |
| 1 | 操作失败（打点失败/未找到目标） | 重跑或查目标 |
| 2 | （保留） | — |
| 3 | 文件不存在（路径无效） | 检查路径 |
| 4 | 运行错误 | 走缺陷回流修脚本 |

---

## 6. 与 harness.py 集成

`harness.py cmd_gate` 写回前自动调 `snapshot snap`（M1 落地）：

```python
# harness.py 内部（伪代码）
def cmd_gate(deck, hours, level):
    # 1. lint 前置（Batch 2 M1）
    lint_rc = run_ooxml_lint(deck)
    if lint_rc == 1:  # ERROR
        return 1
    # 2. 写回前打快照
    run_snapshot_snap(deck, trigger="auto_pre_writeback", gate_exit=0)
    # 3. verify_deck
    return cmd_verify_deck(deck, hours, level)
```

**触发纪律**：
- 每次写回活跃文件**前**打点
- 写回后未变化（sha256 比对相同）→ 跳过
- 里程碑手动触发 `--tag`

---

## 7. 已知坑与限制

1. **rollback 防回滚丢失**：回滚前先把当前活跃版打新快照（`trigger=rollback_snapshot`），确保回滚可逆
2. **sha256 去重**：若两版 hash 相同，第二次 snap 不产生文件——这是设计而非 bug
3. **macOS 与 OneDrive**（v3 修正后低危）：本批不加 macOS 特定清理；`__MACOSX` 残留由 ooxml_lint PKG-002 报 WARN
4. **rollback 用 os.replace**：原子替换，但 Windows 跨盘会失败（macOS/Linux 安全）

---

## 8. 与 WF-2R 的衔接

- **S0**：本批**不动** S0
- **S3**：施工前主理人手动 `snapshot snap` 一次（保护现场）
- **S4 门禁**：harness.py cmd_gate 自动打点 → verify_deck → verifier 复判
- **跨年度治理**：manifest 是索引，淘汰记录可回溯，git 等价轻量 commit log
- **D12 备份膨胀**：通过 K=3 + 500MB + sha256 去重，文件数与总大小受控
