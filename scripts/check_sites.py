#!/usr/bin/env python3
"""Verify that a variable-length repack rewrote references by site, not by value.

This guards the rule in SKILL.md §6.3. Rewriting every word whose value happens
to equal an old offset also hits constants, coordinates, flags and table sizes
that share that value, producing a file that loads but misbehaves. Such damage is
invisible to hash checks (an edited file is supposed to differ) and to interval
coverage (the length did not change). Site-level provenance is the only defence.

Checks performed:
  1. Every byte range that differs between original and rebuilt is covered by a
     declared JoinSite, or by an explicitly declared non-site change.
  2. Site set isomorphism: same count, same offsets, same key_kind; key_value
     follows the declared old -> new mapping.
  3. Value-collision preservation: words equal to some old key but absent from
     the site set are byte-identical in the rebuilt file, and are counted.

Exit code 0 = accept, 1 = reject. Never mutates any input.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path
from typing import Any, Iterable

WIDTH_FMT = {1: "B", 2: "H", 4: "I", 8: "Q"}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise SystemExit(json.dumps(
            {"ok": False, "errors": [{"code": "SITES_MISSING", "detail": f"找不到 {path}"}]},
            ensure_ascii=False, indent=2))
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                raise SystemExit(json.dumps(
                    {"ok": False, "errors": [{"code": "SITES_CORRUPT",
                                              "detail": f"{path}:{lineno} {exc}"}]},
                    ensure_ascii=False, indent=2))
    return out


def read_word(data: bytes, off: int, width: int, little: bool) -> int | None:
    if off + width > len(data):
        return None
    fmt = ("<" if little else ">") + WIDTH_FMT[width]
    return struct.unpack_from(fmt, data, off)[0]


def diff_ranges(a: bytes, b: bytes) -> list[tuple[int, int]]:
    """Byte ranges that differ; positions beyond min length count as differing."""
    ranges: list[tuple[int, int]] = []
    n = min(len(a), len(b))
    i = 0
    while i < n:
        if a[i] != b[i]:
            j = i
            while j < n and a[j] != b[j]:
                j += 1
            ranges.append((i, j))
            i = j
        else:
            i += 1
    if len(a) != len(b):
        ranges.append((n, max(len(a), len(b))))
    return ranges


def overlaps(r: tuple[int, int], s: tuple[int, int]) -> bool:
    return r[0] < s[1] and s[0] < r[1]


def count_value(data: bytes, value: int, width: int, little: bool,
                skip: set[int] | None = None) -> int:
    """Occurrences of `value` at width-aligned offsets, optionally skipping some."""
    n = 0
    for off in range(0, len(data) - width + 1, width):
        if skip and off in skip:
            continue
        if read_word(data, off, width, little) == value:
            n += 1
    return n


def check_collisions(src: bytes, dst: bytes, sites: list[dict[str, Any]],
                     site_offsets: set[int], old_keys: set[int],
                     width: int, little: bool) -> tuple[int, list[dict[str, Any]], str]:
    """Detect by-value rewriting, including when the file length changed.

    Offset-by-offset comparison only works for equal-length output, but by-value
    rewriting is a variable-length phenomenon -- gating this check on equal length
    would disable it in the only case where it can occur. So we count occurrences
    instead of comparing positions.

    A word whose value equals old key K but which is not a declared site must be
    preserved. Correct site-based rewriting therefore leaves exactly as many
    occurrences of K in the output as the original had outside the site set.
    By-value rewriting turns them all into K', so the count drops.

    A count that is too HIGH is not a violation: realignment can create new words
    that happen to equal K. Only a shortfall proves a preserved word was rewritten.
    """
    preserve_offsets = {int(s["site_offset"]) for s in sites
                        if s.get("rewrite_policy") == "preserve"}
    rewritten_offsets = site_offsets - preserve_offsets

    collisions = 0
    violations: list[dict[str, Any]] = []
    for key in sorted(old_keys):
        # Non-site occurrences in the original, plus sites explicitly preserved.
        expected = count_value(src, key, width, little, skip=rewritten_offsets)
        actual = count_value(dst, key, width, little)
        collisions += count_value(src, key, width, little, skip=site_offsets)
        if actual < expected:
            violations.append({"value": key, "expected": expected, "actual": actual})

    method = "offset" if len(src) == len(dst) else "count"
    if method == "offset":
        # Equal length lets us name the exact offset, which is a better diagnostic.
        violations = []
        for off in range(0, len(src) - width + 1, width):
            if off in site_offsets:
                continue
            val = read_word(src, off, width, little)
            if val not in old_keys:
                continue
            if read_word(dst, off, width, little) != val:
                violations.append({"offset": off, "value": val})
    return collisions, violations, method


def check(original: Path, rebuilt: Path, sites_path: Path,
          reloc_path: Path | None, strict_diff: bool) -> dict[str, Any]:
    src = original.read_bytes()
    dst = rebuilt.read_bytes()
    sites = load_jsonl(sites_path)
    errors: list[dict[str, Any]] = []

    # ---- site set isomorphism -------------------------------------------------
    seen_offsets: dict[int, dict[str, Any]] = {}
    for s in sites:
        off = int(s["site_offset"])
        if off in seen_offsets:
            errors.append({"code": "SITE_DUPLICATE",
                           "detail": f"site_offset 0x{off:08X} 重复出现"})
        seen_offsets[off] = s

    old_keys: set[int] = set()
    mapping: dict[int, int] = {}
    for s in sites:
        kv = s.get("key_value")
        if kv is None:
            continue
        old_keys.add(int(kv))
        nv = s.get("new_key_value")
        if nv is not None:
            mapping[int(kv)] = int(nv)

    rewritten = 0
    for s in sites:
        off = int(s["site_offset"])
        width = int(s.get("site_width", 4))
        if width not in WIDTH_FMT:
            errors.append({"code": "SITE_WIDTH",
                           "detail": f"0x{off:08X} 不支持的 site_width={width}"})
            continue
        little = str(s.get("site_endianness", "little")) == "little"
        policy = s.get("rewrite_policy", "rewrite")
        old_val = read_word(src, off, width, little)
        new_val = read_word(dst, off, width, little)
        if old_val is None or new_val is None:
            errors.append({"code": "SITE_OUT_OF_RANGE",
                           "detail": f"站点 0x{off:08X} 超出文件范围"})
            continue
        declared_old = s.get("key_value")
        if declared_old is not None and old_val != int(declared_old):
            errors.append({"code": "SITE_VALUE_DESYNC",
                           "detail": f"站点 0x{off:08X} 原文件值 {old_val} "
                                     f"与声明的 key_value {int(declared_old)} 不符"})
        if policy == "preserve":
            if new_val != old_val:
                errors.append({"code": "PRESERVE_VIOLATED",
                               "detail": f"站点 0x{off:08X} 策略为 preserve 但值已改"
                                         f"（{old_val} -> {new_val}）"})
        else:
            expected = mapping.get(old_val)
            if expected is not None and new_val != expected:
                errors.append({"code": "SITE_MAP_MISMATCH",
                               "detail": f"站点 0x{off:08X} 期望回填 {expected}，实际 {new_val}"})
            if new_val != old_val:
                rewritten += 1

    # ---- value-collision preservation ---------------------------------------
    # Words equal to some old key but NOT declared as sites must be untouched.
    # Runs for variable-length output too -- that is where by-value rewriting
    # actually happens (§6.3).
    collisions = 0
    collision_method = "skipped"
    collision_violations: list[dict[str, Any]] = []
    if old_keys and sites:
        width = int(sites[0].get("site_width", 4))
        little = str(sites[0].get("site_endianness", "little")) == "little"
        if width in WIDTH_FMT:
            collisions, collision_violations, collision_method = check_collisions(
                src, dst, sites, set(seen_offsets), old_keys, width, little)
    for v in collision_violations[:20]:
        if "offset" in v:
            errors.append({
                "code": "VALUE_MATCH_REWRITE",
                "detail": f"偏移 0x{v['offset']:08X} 的值 {v['value']} 等于某个旧键但不是声明站点，"
                          f"却被改写了——这是按值匹配而非按站点改写的特征（§6.3）",
                "offset": v["offset"]})
        else:
            errors.append({
                "code": "VALUE_MATCH_REWRITE",
                "detail": f"值 {v['value']} 等于某个旧键：原文件有 {v['expected']} 处非站点出现，"
                          f"输出中只剩 {v['actual']} 处——非站点位置被按值改写了（§6.3）",
                "value": v["value"]})
    if len(collision_violations) > 20:
        errors.append({"code": "VALUE_MATCH_REWRITE",
                       "detail": f"另有 {len(collision_violations) - 20} 处同类改写未列出"})

    # ---- every diff range must be attributable ------------------------------
    declared: list[tuple[int, int]] = []
    for s in sites:
        off = int(s["site_offset"])
        declared.append((off, off + int(s.get("site_width", 4))))
    reloc_entries: list[dict[str, Any]] = []
    if reloc_path and reloc_path.exists():
        reloc_entries = load_jsonl(reloc_path)
        for r in reloc_entries:
            if "offset" in r and "length" in r:
                o = int(r["offset"])
                declared.append((o, o + int(r["length"])))

    # Byte-offset attribution is only meaningful when the layout did not shift:
    # after an insertion every later byte differs, so every range would be
    # reported. Skipping is recorded explicitly rather than passing silently.
    unattributed: list[tuple[int, int]] = []
    diff_attribution = "checked" if (len(src) == len(dst) or strict_diff) else "skipped-length-changed"
    if diff_attribution == "checked":
        for rng in diff_ranges(src, dst):
            if not any(overlaps(rng, d) for d in declared):
                unattributed.append(rng)
    for rng in unattributed[:20]:
        errors.append({
            "code": "UNATTRIBUTED_DIFF",
            "detail": f"范围 [0x{rng[0]:08X}, 0x{rng[1]:08X}) 发生了改动，"
                      f"但无法追溯到任何 join_id 或声明的重定位记录",
            "start": rng[0], "end": rng[1]})
    if len(unattributed) > 20:
        errors.append({"code": "UNATTRIBUTED_DIFF",
                       "detail": f"另有 {len(unattributed) - 20} 处未归属改动未列出"})

    result = {
        "ok": not errors,
        "original": str(original), "rebuilt": str(rebuilt),
        "original_size": len(src), "rebuilt_size": len(dst),
        "declared_sites": len(sites),
        "rewritten_sites": rewritten,
        "preserved_value_collisions": collisions,
        "collision_check_method": collision_method,
        "diff_attribution": diff_attribution,
        "relocation_entries": len(reloc_entries),
        "errors": errors,
    }
    warnings: list[str] = []
    if collisions == 0 and old_keys:
        warnings.append("preserved_value_collisions 为 0；键域可能过窄，"
                        "或样本中确实没有同值常量（§6.3）")
    if diff_attribution == "skipped-length-changed":
        warnings.append("长度已改变，差异范围归属检查被跳过；"
                        "如需强制检查请加 --strict-diff（§6.3）")
    if warnings:
        result["warnings"] = warnings
    return result


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("original", type=Path)
    ap.add_argument("rebuilt", type=Path)
    ap.add_argument("sites", type=Path, help="ir/join_sites.jsonl")
    ap.add_argument("--relocation-log", type=Path,
                    help="reports/relocation_log.jsonl，声明非站点改动")
    ap.add_argument("--strict-diff", action="store_true",
                    help="即使长度变化也要求每个差异范围可归属")
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(list(argv) if argv is not None else None)

    try:
        result = check(args.original, args.rebuilt, args.sites,
                       args.relocation_log, args.strict_diff)
    except OSError as exc:
        result = {"ok": False, "errors": [{"code": "IO_ERROR", "detail": str(exc)}]}

    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.report:
        args.report.write_text(text, encoding="utf-8")
    write_stdout(text)
    return 0 if result.get("ok") else 1

def write_stdout(text: str) -> None:
    """Write UTF-8 regardless of the console code page (GBK/CP932 consoles
    cannot encode CJK diagnostics)."""
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
