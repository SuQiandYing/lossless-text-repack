#!/usr/bin/env python3
"""Detect extractions that pass every byte-level gate yet found nothing useful.

Enforces SKILL.md §0.1. A tool can reach byte_coverage=1.0, byte-identical
roundtrip, a strict certificate and a green test suite while extracting zero
dialogue -- because those gates measure byte ownership and reversibility, not
whether the target objects were located. This script checks the extraction
*output* instead.

Input is the per-sample extraction report (JSON or JSONL). Required per sample:

    {"sample": "a.scn", "byte_size": 120329,
     "tags": {"msg": 161, "name": 44, "ui": 4},
     "containers": {"strings": 257, "dialog_entries": 96}}   # optional

`containers` enables the order-of-magnitude check; without it that check is
skipped and reported as such rather than silently passing.

Exit code 0 = plausible, 1 = suspicious (requires human confirmation).
Never mutates any input.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

#: 剧本类样本必须命中的类别。缺失即判定为失败：含对话的作品不可能提取到 0 条正文。
#: 这不是启发式推测，而是领域确定性事实（§0.1）。
REQUIRED_TAGS = {"msg"}

#: 单一类别占比超过此值即视为倾斜——通常意味着只命中了某一种结构分支。
SKEW_THRESHOLD = 0.95

#: 抽出条数与容器内同类对象数之比低于此值即视为数量级不符。
MAGNITUDE_RATIO = 0.10

#: 每千字节产出量的跨样本离散度上限（最大值 / 最小值）。
DENSITY_SPREAD = 10.0

#: 容器对象名 -> 应与之数量级相当的 tag。
CONTAINER_EXPECT = {"dialog_entries": "msg", "select_entries": "choice"}


def load_report(path: Path) -> list[dict[str, Any]]:
    """读取报告。接受 JSON 数组、JSONL，或含 rows/samples 键的对象。"""
    text = path.read_text(encoding="utf-8-sig")
    stripped = text.lstrip()
    if stripped.startswith("["):
        rows = json.loads(text)
    elif stripped.startswith("{"):
        obj = json.loads(text)
        for key in ("rows", "samples", "files"):
            if isinstance(obj.get(key), list):
                rows = obj[key]
                break
        else:
            rows = [obj]
    else:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not isinstance(rows, list):
        raise ValueError("报告根节点必须是数组、JSONL 或含 rows/samples 的对象")
    return [r for r in rows if isinstance(r, dict)]


def tag_counts(row: dict[str, Any]) -> dict[str, int]:
    """取出该样本的 tag 计数，兼容几种常见字段名。"""
    for key in ("tags", "tag_counts", "export_tag_counts", "by_tag"):
        value = row.get(key)
        if isinstance(value, dict):
            return {str(k): int(v) for k, v in value.items()
                    if isinstance(v, (int, float))}
    return {}


def sample_name(row: dict[str, Any], index: int) -> str:
    for key in ("sample", "file", "name", "path"):
                                            # path 取尾段，避免报告里出现绝对路径
        value = row.get(key)
        if isinstance(value, str) and value:
            return Path(value).name
    return f"#{index}"


def check_sample(row: dict[str, Any], index: int,
                 required: set[str] | None = None) -> list[dict[str, Any]]:
    """单样本检查。返回问题列表，空列表表示通过。"""
    name = sample_name(row, index)
    tags = tag_counts(row)
    required = REQUIRED_TAGS if required is None else required
    issues: list[dict[str, Any]] = []

    if not tags:
        return [{"sample": name, "code": "NO_TAG_COUNTS",
                 "detail": "报告中没有 tag 计数字段，无法判断产出是否合理；"
                           "请在提取报告里输出 tags{}"}]

    total = sum(tags.values())
    if total == 0:
        return [{"sample": name, "code": "EMPTY_OUTPUT",
                 "detail": "该样本一条文本都没提取到"}]

    # ① 必需类别缺失
    for tag in sorted(required):
        if tags.get(tag, 0) == 0:
            issues.append({
                "sample": name, "code": "REQUIRED_TAG_ZERO",
                "detail": f"tag={tag} 为 0 条，而其余类别共 {total} 条。"
                          f"含对话的剧本不可能没有正文——通常是结构变体未被穷举"
                          f"（§0.2），提取逻辑落在了值为 null 的平铺槽位上",
                "tags": tags})

    # ② 产出高度倾斜
    top_tag, top_n = max(tags.items(), key=lambda kv: kv[1])
    share = top_n / total
    if share > SKEW_THRESHOLD and len(tags) > 1:
        issues.append({
            "sample": name, "code": "SKEWED_OUTPUT",
            "detail": f"tag={top_tag} 占 {share:.1%}（{top_n}/{total}），"
                      f"其余类别接近 0；通常意味着只命中了一种结构分支",
            "tags": tags})

    # ③ 与容器内同类对象数量级不符
    containers = row.get("containers")
    if isinstance(containers, dict):
        for obj_key, tag in CONTAINER_EXPECT.items():
            declared = containers.get(obj_key)
            if not isinstance(declared, (int, float)) or declared <= 0:
                continue
            got = tags.get(tag, 0)
            if got < declared * MAGNITUDE_RATIO:
                issues.append({
                    "sample": name, "code": "MAGNITUDE_MISMATCH",
                    "detail": f"容器内有 {int(declared)} 个 {obj_key}，"
                              f"但只抽出 {got} 条 tag={tag}"
                              f"（低于 {MAGNITUDE_RATIO:.0%} 阈值）",
                    "tags": tags})
    return issues


def check_density(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """跨样本密度离散度。同引擎样本的每千字节产出量不应差一个数量级以上。"""
    points: list[tuple[str, float]] = []
    for i, row in enumerate(rows):
        size = row.get("byte_size") or row.get("size")
        tags = tag_counts(row)
        if not isinstance(size, (int, float)) or size <= 0 or not tags:
            continue
        points.append((sample_name(row, i), sum(tags.values()) / (size / 1000)))
    if len(points) < 2:
        return []
    lo_name, lo = min(points, key=lambda p: p[1])
    hi_name, hi = max(points, key=lambda p: p[1])
    if lo <= 0:
        return [{"code": "ZERO_DENSITY",
                 "detail": f"{lo_name} 的每千字节产出量为 0，而 {hi_name} 为 {hi:.2f}"}]
    if hi / lo > DENSITY_SPREAD:
        return [{"code": "DENSITY_SPREAD",
                 "detail": f"每千字节产出量跨样本差 {hi/lo:.0f} 倍"
                           f"（{lo_name} {lo:.2f} … {hi_name} {hi:.2f}）；"
                           f"通常意味着部分样本的结构变体未被处理"}]
    return []


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("report", type=Path, help="提取报告（JSON / JSONL）")
    ap.add_argument("--require-tag", action="append", default=[],
                    help="追加必需类别，可重复；默认要求 msg")
    ap.add_argument("--allow-zero", action="append", default=[],
                    help="允许该类别为 0（须在报告里写明理由），可重复")
    ap.add_argument("--report-out", type=Path)
    args = ap.parse_args(list(argv) if argv is not None else None)

    required = (REQUIRED_TAGS | set(args.require_tag)) - set(args.allow_zero)

    try:
        rows = load_report(args.report)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _emit({"ok": False, "issues": [{"code": "REPORT_UNREADABLE",
                                        "detail": str(exc)}]}, args.report_out)
        return 1

    issues: list[dict[str, Any]] = []
    for i, row in enumerate(rows):
        issues.extend(check_sample(row, i, required))
    issues.extend(check_density(rows))

    has_containers = any(isinstance(r.get("containers"), dict) for r in rows)
    result = {
        "ok": not issues,
        "samples": len(rows),
        "required_tags": sorted(required),
        "checks_skipped": ([] if has_containers
                           else ["MAGNITUDE_MISMATCH：报告未提供 containers{}"]),
        "issue_count": len(issues),
        "issues": issues[:100],
        "note": "命中任一条即须人工确认，不得以「样本特性」为由放行（§0.1）",
    }
    _emit(result, args.report_out)
    return 0 if result["ok"] else 1


def _emit(result: dict[str, Any], out: Path | None) -> None:
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if out:
        out.write_text(text, encoding="utf-8")
    write_stdout(text)


def write_stdout(text: str) -> None:
    """以 UTF-8 输出，不受控制台代码页限制（GBK/CP932 无法编码 CJK 诊断）。"""
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
