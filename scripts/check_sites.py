#!/usr/bin/env python3
"""Verify declared reference-site writes and complete byte-change attribution.

No engine layout is guessed. Equal-length files use positional interval union.
Variable-length files require --layout-map JSONL: old_offset, old_length,
new_offset, new_length, kind=preserve|changed, and reason for changed spans.
Both coordinate spaces must be fully covered without overlaps. Preserve spans
are compared exactly. Changed spans are explicit trusted declarations, NOT proof
of correct compression or semantic content. Their semantic checks belong to the
format-specific reparser. Optional --rebuilt-sites verifies the reparsed site set.

Exit 0=pass within verification_scope, 1=fail, 2=not_verified. A missing layout
map never becomes a pass merely because a collision-count heuristic passed.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
import hashlib
import json
import re
import struct
import sys
from pathlib import Path
from typing import Any, Iterable

WIDTH_FMT = {1: "B", 2: "H", 4: "I", 8: "Q"}


class Reject(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code, self.detail = code, detail


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise Reject("CLI_ARGUMENTS", message)


def integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not (isinstance(value, int) or isinstance(value, str)
            and re.fullmatch(r"(?:[0-9]+|0[xX][0-9a-fA-F]+)", value)):
        raise Reject("SCHEMA", f"{label} must be a non-negative integer")
    try:
        number = int(value, 16 if value.lower().startswith("0x") else 10) if isinstance(value, str) else value
    except ValueError as exc:
        raise Reject("SCHEMA", f"{label}: integer too large to parse") from exc
    if number < 0:
        raise Reject("SCHEMA", f"{label} must be non-negative")
    return number


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError(f"duplicate JSON field {key}")
            obj[key] = value
        return obj

    def invalid_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant {value}")

    out = []
    for lineno, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid_constant)
        except (ValueError, RecursionError) as exc:
            raise Reject("JSON_CORRUPT", f"{path}:{lineno}: {exc}") from exc
        if not isinstance(row, dict):
            raise Reject("SCHEMA", f"{path}:{lineno}: expected JSON object")
        out.append(row)
    return out


def read_word(data: bytes, off: int, width: int, little: bool) -> int | None:
    if off < 0 or width not in WIDTH_FMT or off + width > len(data):
        return None
    return struct.unpack_from(("<" if little else ">") + WIDTH_FMT[width], data, off)[0]


def diff_ranges(a: bytes, b: bytes) -> list[tuple[int, int]]:
    ranges, start = [], None
    for off in range(min(len(a), len(b))):
        if a[off] != b[off] and start is None:
            start = off
        elif a[off] == b[off] and start is not None:
            ranges.append((start, off))
            start = None
    if start is not None:
        ranges.append((start, min(len(a), len(b))))
    if len(a) != len(b):
        ranges.append((min(len(a), len(b)), max(len(a), len(b))))
    return ranges


def overlaps(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if start == end:
            continue
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(end, out[-1][1]))
        else:
            out.append((start, end))
    return out


def uncovered(rng: tuple[int, int], declared: list[tuple[int, int]], *, merged: bool = False) -> list[tuple[int, int]]:
    """Subtract the union of declarations, not merely test intersection."""
    cursor, end = rng
    out = []
    for start, stop in declared if merged else merge_ranges(declared):
        if stop <= cursor:
            continue
        if start >= end:
            break
        if start > cursor:
            out.append((cursor, min(start, end)))
        cursor = max(cursor, stop)
        if cursor >= end:
            break
    if cursor < end:
        out.append((cursor, end))
    return out


def validate_sites(rows: list[dict[str, Any]], size: int, label: str) -> list[dict[str, Any]]:
    spans = []
    for row in rows:
        row["site_offset"] = integer(row.get("site_offset"), "site_offset")
        row["site_width"] = integer(row.get("site_width", 4), "site_width")
        off, width = row["site_offset"], row["site_width"]
        if width not in WIDTH_FMT:
            raise Reject("SITE_WIDTH", f"{label}: unsupported site width {width}")
        if off + width > size:
            raise Reject("SITE_OUT_OF_RANGE", f"{label}: site [{off},{off + width}) exceeds file")
        row["site_endianness"] = row.get("site_endianness", "little")
        if row["site_endianness"] not in ("little", "big"):
            raise Reject("SCHEMA", "site_endianness must be little or big")
        row["rewrite_policy"] = row.get("rewrite_policy", "rewrite")
        if row["rewrite_policy"] not in ("rewrite", "preserve"):
            raise Reject("SCHEMA", "rewrite_policy must be rewrite or preserve")
        for field in ("key_value", "new_key_value"):
            if field == "key_value" or field in row:
                row[field] = integer(row.get(field), field)
                if row[field] >= 1 << (8 * width):
                    raise Reject("SCHEMA", f"{field} exceeds site width")
        if "new_site_offset" in row:
            row["new_site_offset"] = integer(row["new_site_offset"], "new_site_offset")
        if row["rewrite_policy"] == "preserve" and row.get("new_key_value", row["key_value"]) != row["key_value"]:
            raise Reject("SCHEMA", "preserve site cannot declare a different new_key_value")
        if "key_kind" in row and (not isinstance(row["key_kind"], str) or not row["key_kind"]):
            raise Reject("SCHEMA", "key_kind must be a nonempty string")
        if "src_id" in row and (not isinstance(row["src_id"], str) or not row["src_id"]):
            raise Reject("SCHEMA", "src_id must be a nonempty string")
        spans.append((off, off + width))
    spans.sort()
    for a, b in zip(spans, spans[1:]):
        if overlaps(a, b):
            raise Reject("SITE_DUPLICATE", f"{label}: overlapping site declarations")
    sources = {row["src_id"] for row in rows if "src_id" in row}
    if len(sources) > 1:
        raise Reject("MIXED_SOURCES", "filter merged site records to one source before checking")
    return rows


def validate_layout(path: Path, src: bytes, dst: bytes) -> list[dict[str, Any]]:
    rows = load_jsonl(path)
    if not rows:
        raise Reject("EMPTY_LAYOUT", "layout map contains no spans")
    for row in rows:
        for field in ("old_offset", "old_length", "new_offset", "new_length"):
            row[field] = integer(row.get(field), field)
        if not row["old_length"] and not row["new_length"]:
            raise Reject("LAYOUT_EMPTY_SPAN", "zero-length spans cannot cover either file")
        if row.get("kind") not in ("preserve", "changed"):
            raise Reject("SCHEMA", "layout kind must be preserve or changed")
        if row["kind"] == "changed" and (not isinstance(row.get("reason"), str) or not row["reason"].strip()):
            raise Reject("SCHEMA", "changed layout spans require reason")
        if row["kind"] == "preserve" and row["old_length"] != row["new_length"]:
            raise Reject("LAYOUT_PRESERVE", "preserve span lengths must match")
    for prefix, data in (("old", src), ("new", dst)):
        cursor = 0
        spans = []
        for row in rows:
            off, length = row[prefix + "_offset"], row[prefix + "_length"]
            if off > len(data) or off + length > len(data):
                raise Reject("LAYOUT_BOUNDS", f"{prefix} span outside file")
            if length:
                spans.append((off, off + length))
        for start, end in sorted(spans):
            if start != cursor:
                raise Reject("LAYOUT_COVERAGE", f"{prefix} layout has a gap or overlap at {cursor}")
            cursor = end
        if cursor != len(data):
            raise Reject("LAYOUT_COVERAGE", f"{prefix} layout does not cover tail at {cursor}")
    return rows


def mapped_offset(off: int, width: int, layout: list[dict[str, Any]]) -> int | None:
    for row in layout:
        if row["old_length"] == row["new_length"] and row["old_offset"] <= off and off + width <= row["old_offset"] + row["old_length"]:
            return row["new_offset"] + off - row["old_offset"]
    return None


def check(original: Path, rebuilt: Path, sites_path: Path,
          reloc_path: Path | None = None, strict_diff: bool = False,
          layout_path: Path | None = None, rebuilt_sites_path: Path | None = None) -> dict[str, Any]:
    src, dst = original.read_bytes(), rebuilt.read_bytes()
    sites = validate_sites(load_jsonl(sites_path), len(src), "original")
    errors: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    if not src or not dst:
        raise Reject("EMPTY_BINARY", "empty binaries require a format-specific verifier")
    layout = validate_layout(layout_path, src, dst) if layout_path else []
    relocations = load_jsonl(reloc_path) if reloc_path else []
    declared = [(s["site_offset"], s["site_offset"] + s["site_width"]) for s in sites]
    for row in relocations:
        off, length = integer(row.get("offset"), "offset"), integer(row.get("length"), "length")
        if not length or off + length > max(len(src), len(dst)):
            raise Reject("RELOCATION_BOUNDS", "relocation range is empty or outside files")
        declared.append((off, off + length))
    declared = merge_ranges(declared)
    digest = hashlib.sha256(src).hexdigest()
    rewritten, new_sites = 0, []
    for site in sites:
        off, width = site["site_offset"], site["site_width"]
        if "source_artifact_hash" in site and site["source_artifact_hash"] != digest:
            errors.append({"code": "SOURCE_HASH_MISMATCH", "detail": f"site {off} belongs to another source hash"})
        new_off = site.get("new_site_offset")
        if new_off is None:
            new_off = mapped_offset(off, width, layout) if layout else off if len(src) == len(dst) else None
        little = site["site_endianness"] == "little"
        old_value = read_word(src, off, width, little)
        if old_value != site["key_value"]:
            errors.append({"code": "SITE_VALUE_DESYNC", "detail": f"site {off}: original value does not match key_value"})
        if new_off is None:
            pending.append({"code": "SITE_POSITION_UNVERIFIED", "detail": f"site {off}: declare new_site_offset or a length-preserving mapped span"})
            continue
        new_value = read_word(dst, new_off, width, little)
        if new_value is None:
            errors.append({"code": "SITE_OUT_OF_RANGE", "detail": f"rebuilt site {new_off} exceeds file"})
            continue
        expected = site["key_value"] if site["rewrite_policy"] == "preserve" else site.get("new_key_value", site["key_value"])
        if new_value != expected:
            errors.append({"code": "PRESERVE_VIOLATED" if site["rewrite_policy"] == "preserve" else "SITE_MAP_MISMATCH",
                           "detail": f"site {off} -> {new_off}: expected {expected}, got {new_value}"})
        rewritten += new_value != old_value
        # Do not carry old-side policies/new_key_value into reparsed validation.
        new_sites.append({"site_offset": new_off, "site_width": width,
                          "site_endianness": site["site_endianness"], "key_value": expected,
                          **({"key_kind": site["key_kind"]} if "key_kind" in site else {})})
    if new_sites:
        validate_sites(new_sites, len(dst), "expected rebuilt")

    compare_spans: list[tuple[int, int, int]] = []
    if layout:
        for row in layout:
            a, n, b, m = row["old_offset"], row["old_length"], row["new_offset"], row["new_length"]
            if row["kind"] == "preserve":
                if src[a:a + n] != dst[b:b + m]:
                    errors.append({"code": "PRESERVE_SPAN_CHANGED", "detail": f"preserve span [{a},{a + n}) -> [{b},{b + m}) differs"})
                compare_spans.append((a, a + n, b))
        attribution = "checked-layout-map"
    elif len(src) == len(dst) or strict_diff:
        for rng in diff_ranges(src, dst):
            for start, end in uncovered(rng, declared, merged=True):
                errors.append({"code": "UNATTRIBUTED_DIFF", "detail": f"undeclared changed bytes [{start},{end})", "start": start, "end": end})
        attribution = "checked-positional" if len(src) == len(dst) else "checked-positional-only"
        if len(src) == len(dst):
            compare_spans = [(0, len(src), 0)]
    else:
        attribution = "not_verified-length-changed"
    if len(src) != len(dst) and not layout:
        pending.append({"code": "LAYOUT_UNVERIFIED", "detail": "variable length requires --layout-map; --strict-diff only adds a positional check"})

    collisions = 0
    union = merge_ranges(declared)
    union_starts = [start for start, _ in union]
    groups: dict[tuple[int, str], set[int]] = {}
    for site in sites:
        groups.setdefault((site["site_width"], site["site_endianness"]), set()).add(site["key_value"])
    for (width, endian), keys in groups.items():
        for start, end, new_start in compare_spans:
            for off in range(start, end - width + 1):
                window = (off, off + width)
                # A window intersecting a declared write is not a preserved word.
                insertion = bisect_right(union_starts, window[1] - 1) - 1
                if insertion >= 0 and union[insertion][1] > window[0]:
                    continue
                value = read_word(src, off, width, endian == "little")
                if value in keys:
                    collisions += 1
                    actual = read_word(dst, new_start + off - start, width, endian == "little")
                    if value != actual:
                        errors.append({"code": "VALUE_MATCH_REWRITE", "detail": f"non-site word {off} matching key {value} was changed", "offset": off})
    collision_method = "mapped-exact" if layout else "offset-exact" if len(src) == len(dst) else "not_verified"
    isomorphism = "not_requested"
    if rebuilt_sites_path:
        reparsed = validate_sites(load_jsonl(rebuilt_sites_path), len(dst), "reparsed rebuilt")
        if pending:
            isomorphism = "not_verified"
        else:
            def signature(row: dict[str, Any]) -> tuple[Any, ...]:
                return (row["site_offset"], row["site_width"], row["site_endianness"], row.get("key_kind"), row["key_value"])
            if sorted(map(signature, new_sites)) != sorted(map(signature, reparsed)):
                errors.append({"code": "SITE_SET_MISMATCH", "detail": "reparsed site count/position/width/endianness/key kind/value differs"})
            isomorphism = "checked"
    status = "fail" if errors else "not_verified" if pending else "pass"
    return {"ok": status == "pass", "status": status, "errors": errors, "not_verified": pending,
            "original": str(original), "rebuilt": str(rebuilt),
            "original_size": len(src), "rebuilt_size": len(dst),
            "declared_sites": len(sites), "rewritten_sites": rewritten,
            "preserved_value_collisions": collisions, "collision_check_method": collision_method,
            "diff_attribution": attribution, "relocation_entries": len(relocations),
            "site_set_isomorphism": isomorphism,
            "verification_scope": "declared-byte-writes-and-layout" + ("+reparsed-site-set" if rebuilt_sites_path else ""),
            "semantic_reparse": "not_checked_by_this_tool"}


def main(argv: Iterable[str] | None = None) -> int:
    ap = Parser(description=__doc__)
    ap.add_argument("original", type=Path)
    ap.add_argument("rebuilt", type=Path)
    ap.add_argument("sites", type=Path)
    ap.add_argument("--relocation-log", type=Path)
    ap.add_argument("--strict-diff", action="store_true", help="without --layout-map, force positional attribution even for length changes; not a substitute for mapping")
    ap.add_argument("--layout-map", type=Path, help="explicit complete old/new span mapping JSONL")
    ap.add_argument("--rebuilt-sites", type=Path, help="independently reparsed join-sites JSONL")
    ap.add_argument("--report", type=Path)
    try:
        args = ap.parse_args(list(argv) if argv is not None else None)
    except Reject as exc:
        write_stdout(json.dumps({"ok": False, "status": "fail", "errors": [{"code": exc.code, "detail": exc.detail}]}) + "\n")
        return 1
    try:
        protected = [args.original, args.rebuilt, args.sites, args.relocation_log, args.layout_map, args.rebuilt_sites]
        if args.report and args.report.resolve() in {path.resolve() for path in protected if path is not None}:
            args.report = None
            raise Reject("INPUT_REPORT_COLLISION", "--report must not overwrite an input")
        result = check(args.original, args.rebuilt, args.sites, args.relocation_log,
                       args.strict_diff, args.layout_map, args.rebuilt_sites)
    except Reject as exc:
        result = {"ok": False, "status": "fail", "errors": [{"code": exc.code, "detail": exc.detail}]}
    except (OSError, UnicodeError) as exc:
        result = {"ok": False, "status": "fail", "errors": [{"code": "IO_ERROR", "detail": str(exc)}]}
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.report:
        try:
            args.report.write_text(text, encoding="utf-8")
        except OSError as exc:
            result.update(ok=False, status="fail")
            result["errors"].append({"code": "REPORT_IO_ERROR", "detail": str(exc)})
            text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    write_stdout(text)
    return {"pass": 0, "fail": 1, "not_verified": 2}[result["status"]]


def write_stdout(text: str) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="strict")
    except (AttributeError, OSError):
        pass
    sys.stdout.write(text)


if __name__ == "__main__":
    raise SystemExit(main())
