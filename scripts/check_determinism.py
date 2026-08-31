#!/usr/bin/env python3
"""Verify that parsing and rendering are deterministic, and that repack changes
the output exactly when edits exist.

Enforces SKILL.md §2.4, §2.6 and §6.0. Three properties are checked, each of
which a build can violate while every byte-level gate stays green:

  1. Render determinism   Running the tool twice on one input must produce
                          byte-identical artifacts. §2.6's diff mechanism is
                          meaningless without it, and §8 requires reproducible
                          hashes.
  2. Zero-edit identity   With no edits, the rebuilt file must equal the source
                          byte for byte.
  3. Edit visibility      With edits, the rebuilt file must DIFFER from the
                          source. An unchanged hash means the edit was silently
                          dropped -- the failure mode that "hash matches" style
                          checks report as success.

Property 3 is the inverse of property 2, and conflating them is the specific
mistake this script exists to catch.

Usage:
    check_determinism.py rerun  ARTIFACT_A ARTIFACT_B [...]   pairs of runs
    check_determinism.py edit   SOURCE REBUILT --edited | --no-edit

Exit code 0 = holds, 1 = violated. Never mutates any input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Iterable

BLOCK = 1 << 20


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(BLOCK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def first_diff(a: Path, b: Path) -> dict[str, Any] | None:
    """首个差异位置。相同返回 None；不整块读入，支持大文件。"""
    pos = 0
    with a.open("rb") as fa, b.open("rb") as fb:
        while True:
            ba, bb = fa.read(BLOCK), fb.read(BLOCK)
            if not ba and not bb:
                return None
            n = min(len(ba), len(bb))
            for i in range(n):
                if ba[i] != bb[i]:
                    return {"offset": pos + i,
                            "a": f"0x{ba[i]:02X}", "b": f"0x{bb[i]:02X}"}
            if len(ba) != len(bb):
                return {"offset": pos + n, "a_len": a.stat().st_size,
                        "b_len": b.stat().st_size, "reason": "长度不同"}
            pos += n


def cmd_rerun(pairs: list[Path]) -> dict[str, Any]:
    """两次运行的产物必须逐字节相同。"""
    if len(pairs) % 2:
        return {"ok": False, "issues": [{
            "code": "ODD_ARGUMENTS",
            "detail": "rerun 需要成对的产物路径（第一次运行、第二次运行）"}]}
    issues: list[dict[str, Any]] = []
    checked: list[dict[str, Any]] = []
    for a, b in zip(pairs[0::2], pairs[1::2]):
        if not a.is_file() or not b.is_file():
            issues.append({"code": "MISSING_ARTIFACT",
                           "detail": f"找不到 {a if not a.is_file() else b}"})
            continue
        ha, hb = sha256(a), sha256(b)
        same = ha == hb
        checked.append({"a": str(a), "b": str(b), "identical": same,
                        "sha256": ha if same else None})
        if not same:
            issues.append({
                "code": "RENDER_NONDETERMINISTIC",
                "detail": f"{a.name} 两次运行产物不同（首处差异见 first_diff）；"
                          f"§2.6 的 diff 机制与 §8 的可复现哈希均依赖此性质",
                "first_diff": first_diff(a, b),
                "sha256_a": ha, "sha256_b": hb})
    return {"ok": not issues, "mode": "rerun",
            "pairs_checked": len(checked), "artifacts": checked,
            "issue_count": len(issues), "issues": issues}


def cmd_edit(source: Path, rebuilt: Path, edited: bool) -> dict[str, Any]:
    """零编辑须逐字节相同；有编辑须不同。两者判定方向相反，不可混用。"""
    issues: list[dict[str, Any]] = []
    for p in (source, rebuilt):
        if not p.is_file():
            return {"ok": False, "mode": "edit", "issues": [{
                "code": "MISSING_FILE", "detail": f"找不到 {p}"}]}

    hs, hr = sha256(source), sha256(rebuilt)
    same = hs == hr
    diff = None if same else first_diff(source, rebuilt)

    if edited and same:
        issues.append({
            "code": "EDIT_LOST",
            "detail": "声明有编辑，但重建结果与原件哈希相同——编辑未生效或被静默丢弃。"
                      "把「与原件哈希相同」当作编辑后的成功条件，正是本检查要拦住的"
                      "失败模式（§6.0）",
            "sha256": hs})
    if not edited and not same:
        issues.append({
            "code": "ZERO_EDIT_MISMATCH",
            "detail": "声明零编辑，但重建结果与原件不同——解析或重序列化存在缺陷；"
                      "此步通过之前禁止进入任何编辑流程（§9）",
            "first_diff": diff,
            "sha256_source": hs, "sha256_rebuilt": hr})

    return {
        "ok": not issues, "mode": "edit",
        "declared": "edited" if edited else "no-edit",
        "source_size": source.stat().st_size,
        "rebuilt_size": rebuilt.stat().st_size,
        "size_delta": rebuilt.stat().st_size - source.stat().st_size,
        "identical": same,
        "sha256_source": hs, "sha256_rebuilt": hr,
        "first_diff": diff,
        "issue_count": len(issues), "issues": issues,
    }


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="mode", required=True)

    p_rerun = sub.add_parser("rerun", help="校验两次运行产物逐字节相同")
    p_rerun.add_argument("artifacts", type=Path, nargs="+",
                         help="成对给出：第一次产物 第二次产物 …")
    p_rerun.add_argument("--report-out", type=Path)

    p_edit = sub.add_parser("edit", help="校验编辑是否如实反映在输出中")
    p_edit.add_argument("source", type=Path)
    p_edit.add_argument("rebuilt", type=Path)
    g = p_edit.add_mutually_exclusive_group(required=True)
    g.add_argument("--edited", action="store_true", help="已修改译文：哈希必须改变")
    g.add_argument("--no-edit", action="store_true", help="零编辑：哈希必须相同")
    p_edit.add_argument("--report-out", type=Path)

    args = ap.parse_args(list(argv) if argv is not None else None)
    try:
        if args.mode == "rerun":
            result = cmd_rerun(args.artifacts)
        else:
            result = cmd_edit(args.source, args.rebuilt, args.edited)
    except OSError as exc:
        result = {"ok": False, "issues": [{"code": "IO_ERROR", "detail": str(exc)}]}

    _emit(result, args.report_out)
    return 0 if result.get("ok") else 1


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
