#!/usr/bin/env python3
"""Verify that structural shape variants were enumerated, not sampled.

Enforces SKILL.md §0.2 and §7.1.5. Same-engine works drift in structure: a
`texts[]` entry may be a 6/9-slot flat array in one title and a 5-slot array
with the body nested inside a language list in another. Handling only the known
shape yields zero extraction without any error.

This script compares observed shape signatures against the shapes declared by
the dialect, and fails when any of the following holds:

    · an observed signature has no declared handler        UNDECLARED_SHAPE
    · a declared shape was never hit                       UNUSED_SHAPE
    · a shape matched entries but produced no text          BARREN_SHAPE
    · the signature distribution differs from the baseline  DISTRIBUTION_DRIFT

The last two are the ones that pass every byte-level gate. A declared shape that
never matches is equally dangerous: the declaration exists, so review assumes
the variant is covered, while extraction silently falls to another branch.

Input is a shape report:

    {"declared": ["9-slot-flat", "5-slot-nested"],
     "observed": {"5-slot-nested": {"entries": 607, "texts": 1271}},
     "unmatched": {"7-slot-unknown": 12}}          # optional

Exit code 0 = enumerated, 1 = incomplete. Never mutates any input.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable


def load_json(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict):
        raise ValueError("形态报告根节点必须是对象")
    return obj


def normalize_observed(raw: Any) -> dict[str, dict[str, int]]:
    """接受 {sig: n} 或 {sig: {entries, texts}} 两种写法。"""
    out: dict[str, dict[str, int]] = {}
    if not isinstance(raw, dict):
        return out
    for sig, value in raw.items():
        if isinstance(value, dict):
            out[str(sig)] = {
                "entries": int(value.get("entries", 0)),
                # texts 缺省为 -1 表示"未提供"，与真正的 0 区分开
                "texts": int(value.get("texts", -1)),
            }
        elif isinstance(value, (int, float)):
            out[str(sig)] = {"entries": int(value), "texts": -1}
    return out


def check(report: dict[str, Any], baseline: dict[str, Any] | None,
          corpus_wide: bool = False) -> dict[str, Any]:
    declared = {str(s) for s in report.get("declared", [])}
    observed = normalize_observed(report.get("observed"))
    unmatched = report.get("unmatched") or {}
    issues: list[dict[str, Any]] = []
    advisories: list[dict[str, Any]] = []

    if not declared:
        issues.append({"code": "NO_DECLARED_SHAPES",
                       "detail": "方言未声明任何形态，无法判断变体是否穷举"})
    if not observed and not unmatched:
        issues.append({"code": "NO_OBSERVATION",
                       "detail": "报告中没有形态统计；须先遍历全部语料统计签名，"
                                 "不得仅抽查前若干文件（§0.2）"})

    # ① 观测到但未声明：提取逻辑对这些条目无处理分支
    for sig, n in sorted(unmatched.items()):
        issues.append({
            "code": "UNDECLARED_SHAPE", "shape": str(sig),
            "detail": f"形态 {sig} 出现 {int(n)} 次但无声明处理分支；"
                      f"须显式处理或显式记为 unresolved，不得回落到已知分支"})
    for sig in sorted(set(observed) - declared):
        issues.append({
            "code": "UNDECLARED_SHAPE", "shape": sig,
            "detail": f"形态 {sig} 命中 {observed[sig]['entries']} 个条目但未在方言中声明"})

    # ② 声明了却从未命中：声明形同虚设，而审阅会误以为该变体已覆盖。
    # 仅在全语料统计（--corpus-wide）下判定为失败：单个文件只呈现部分形态是正常的，
    # 逐文件判定会产生大量假阳性。
    unused = sorted(declared - set(observed))
    for sig in unused:
        entry = {
            "code": "UNUSED_SHAPE", "shape": sig,
            "detail": f"形态 {sig} 已声明但覆盖率为 0；判定条件可能写错，"
                      f"而既有分支恰好「成功」返回空结果（§7.1.5）"}
        if corpus_wide:
            issues.append(entry)
        else:
            advisories.append({**entry, "note": "单样本统计，全语料下才判定失败"})

    # ③ 命中了条目却没产出文本：正是全部门禁通过而结果为空的情形
    for sig, stat in sorted(observed.items()):
        if stat["entries"] > 0 and stat["texts"] == 0:
            issues.append({
                "code": "BARREN_SHAPE", "shape": sig,
                "detail": f"形态 {sig} 匹配了 {stat['entries']} 个条目却提取出 0 条文本；"
                          f"通常是该形态的文本位于嵌套层，而提取读了平铺槽位"})

    # ④ 与基线的分布漂移：换样本后形态分布不同即提取逻辑可能失配
    drift: list[dict[str, Any]] = []
    if baseline:
        base = normalize_observed(baseline.get("observed"))
        for sig in sorted(set(base) - set(observed)):
            drift.append({"shape": sig, "baseline": base[sig]["entries"], "now": 0})
        for sig in sorted(set(observed) - set(base)):
            drift.append({"shape": sig, "baseline": 0, "now": observed[sig]["entries"]})
        if drift:
            issues.append({
                "code": "DISTRIBUTION_DRIFT", "changes": drift,
                "detail": f"形态分布与基线不同（{len(drift)} 处）；"
                          f"新样本出现基线中没有的形态时须先确认已处理（§0.2）"})

    total_entries = sum(s["entries"] for s in observed.values())
    total_texts = sum(s["texts"] for s in observed.values() if s["texts"] >= 0)
    return {
        "ok": not issues,
        "declared_shapes": sorted(declared),
        "observed_shapes": {k: v for k, v in sorted(observed.items())},
        "total_entries": total_entries,
        "total_texts": total_texts,
        "unmatched_signatures": {str(k): int(v) for k, v in sorted(unmatched.items())},
        "corpus_wide": corpus_wide,
        "issue_count": len(issues),
        "issues": issues[:100],
        "advisories": advisories[:50],
        "note": "先统计形态，再实现提取逻辑；未见过的签名必须显式处理或记为 unresolved",
    }


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("shapes", type=Path, help="形态报告 JSON")
    ap.add_argument("--baseline", type=Path,
                    help="既有语料的形态报告，用于检出分布漂移")
    ap.add_argument("--corpus-wide", action="store_true",
                    help="报告覆盖全部语料；此时「声明未命中」判定为失败而非提示")
    ap.add_argument("--report-out", type=Path)
    args = ap.parse_args(list(argv) if argv is not None else None)

    try:
        report = load_json(args.shapes)
        baseline = load_json(args.baseline) if args.baseline else None
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _emit({"ok": False, "issues": [{"code": "REPORT_UNREADABLE",
                                        "detail": str(exc)}]}, args.report_out)
        return 1

    result = check(report, baseline, corpus_wide=args.corpus_wide)
    _emit(result, args.report_out)
    return 0 if result["ok"] else 1


def _emit(result: dict[str, Any], out: Path | None) -> None:
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if out:
        out.write_text(text, encoding="utf-8")
    write_stdout(text)


def write_stdout(text: str) -> None:
    """以 UTF-8 输出，不受控制台代码页限制。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    try:
        sys.stdout.write(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(text.encode("utf-8", "replace"))


if __name__ == "__main__":
    raise SystemExit(main())
