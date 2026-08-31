#!/usr/bin/env python3
"""Validate a double-line text file against the IR that produced it.

Enforces the 13-point import checklist of SKILL.md §4.9: header integrity,
source hash match, shard completeness, unique fixed-width idx, tag agreement,
no mixed separators, the source line acting as a verification anchor, frozen
entries left untouched, target encoding representability, byte-length limits,
placeholder integrity, and a non-empty translation line.

Batch input is routed per source. §2.3 stores every source in one merged
library, so `idx` is only unique within a `src_id`; each text file is matched to
its source by the `src_sha256` in its header, which is what that field exists
for. Reading the library as one flat {idx: entry} table would let entries from
different sources overwrite each other.

Exit code 0 = accept, 1 = reject. Never mutates any input.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

ORIG_MARK = "○"  # ○
TRAN_MARK = "●"  # ●

# §4.6: idx is fixed-width decimal in all three positions. Fixed width removes
# separator ambiguity; a variable-width idx is a format violation, not a
# tolerated variant. --idx-width overrides for dialects declaring another width.
IDX_WIDTH = 8

# Key for the single implicit group used when the library predates src_id.
ANY_SRC = "*"

ORIG_RE = re.compile(r"^○(?P<idx>\d+)○(?P<tag>[a-z_]+)○(?P<text>.*)$")
TRAN_RE = re.compile(r"^●(?P<idx>\d+)●(?P<tag>[a-z_]+)●(?P<text>.*)$")
PLACEHOLDER_RE = re.compile(r"\{\{([0-9A-F]{2})(?::[0-9A-F]{2})*\}\}")
PLACEHOLDER_LOOSE_RE = re.compile(r"\{\{[^}]*\}\}")

CORE_TAGS = {"name", "msg", "choice", "label", "ui", "system", "ruby", "misc"}
POLICIES = {"translatable", "length-locked", "review-required", "frozen"}

# Substitutions a text editor may silently apply. Catching them is the main
# reason the source line is compared character by character.
EDITOR_DAMAGE = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "…": "...", "–": "-", "—": "-",
}


class Reject(Exception):
    def __init__(self, code: str, detail: str, **ctx: Any) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.ctx = ctx


def parse_header(lines: list[str]) -> dict[str, Any]:
    """Header must occupy the first four lines (rule §4.6)."""
    if len(lines) < 4:
        raise Reject("HEADER_TRUNCATED", f"文件头需要 4 行，实际 {len(lines)} 行")
    hdr: dict[str, Any] = {}
    m = re.match(r"^#\s*TEXT/(?P<ver>\d+)\s+(?P<rest>.*)$", lines[0])
    if not m:
        raise Reject("HEADER_LINE1", f"第 1 行不是 '# TEXT/N …'：{lines[0][:60]!r}")
    hdr["format_version"] = int(m.group("ver"))
    for key, val in re.findall(r"(\w+)=(\S+)", m.group("rest")):
        hdr[key] = val
    for required in ("ir", "tool", "src_sha256"):
        if required not in hdr:
            raise Reject("HEADER_FIELD", f"文件头缺 {required}=")

    if not lines[1].startswith("# encoding"):
        raise Reject("HEADER_LINE2", "第 2 行必须是 '# encoding …'")
    enc = dict(re.findall(r"(\w+)=(\S+)", lines[1]))
    for required in ("source", "target", "file"):
        if required not in enc:
            raise Reject("HEADER_FIELD", f"encoding 行缺 {required}=")
    hdr["encoding"] = enc

    if not lines[2].startswith("# scope"):
        raise Reject("HEADER_LINE3", "第 3 行必须是 '# scope …'")
    scope = dict(re.findall(r"(\w+)=(\S+)", lines[2]))
    if scope.get("kind") not in {"all", "idx-range", "partition"}:
        raise Reject("SCOPE_KIND", f"scope kind 非法：{scope.get('kind')!r}")
    part = scope.get("part", "1/1")
    pm = re.fullmatch(r"(\d+)/(\d+)", part)
    if not pm:
        raise Reject("SCOPE_PART", f"part 需为 K/N：{part!r}")
    scope["part_index"], scope["part_total"] = int(pm.group(1)), int(pm.group(2))
    if not 1 <= scope["part_index"] <= scope["part_total"]:
        raise Reject("SCOPE_PART", f"part 越界：{part}")
    hdr["scope"] = scope

    if not lines[3].startswith("# tags"):
        raise Reject("HEADER_LINE4", "第 4 行必须是 '# tags …'")
    return hdr


def meta_of(comment: str) -> dict[str, str]:
    return dict(re.findall(r"(\w+)=([^\s]+)", comment))


def placeholder_bytes(text: str) -> list[int]:
    out: list[int] = []
    for m in PLACEHOLDER_RE.finditer(text):
        out.extend(int(b, 16) for b in m.group(0)[2:-2].split(":"))
    return out


def check_placeholders(idx: int, src: str, dst: str) -> None:
    """Placeholders must survive translation byte-for-byte (§4.5)."""
    for m in PLACEHOLDER_LOOSE_RE.finditer(dst):
        if not PLACEHOLDER_RE.fullmatch(m.group(0)):
            raise Reject("PLACEHOLDER_BROKEN",
                         f"idx={idx} 占位符格式非法：{m.group(0)!r}（须为大写 {{{{XX}}}} 或 {{{{XX:YY}}}}）",
                         idx=idx)
    a, b = placeholder_bytes(src), placeholder_bytes(dst)
    if a != b:
        raise Reject("PLACEHOLDER_BROKEN",
                     f"idx={idx} 占位符字节不一致：原文 {a}，译文 {b}", idx=idx)


def visible_len_bytes(text: str, codec: str) -> int:
    """Encoded length with placeholders counted as their raw bytes."""
    total = 0
    pos = 0
    for m in PLACEHOLDER_RE.finditer(text):
        total += len(text[pos:m.start()].encode(codec))
        total += len(m.group(0)[2:-2].split(":"))
        pos = m.end()
    total += len(text[pos:].encode(codec))
    return total


def diagnose_source_mismatch(expected: str, actual: str) -> str:
    if unicodedata.normalize("NFKC", expected) == unicodedata.normalize("NFKC", actual):
        return "疑似编辑器做了全角/半角或兼容字符替换"
    if expected.rstrip() == actual.rstrip():
        return "疑似行尾空白被剥离"
    if any(bad in actual for bad in EDITOR_DAMAGE):
        return "疑似编辑器把直引号/省略号替换成了排版字符"
    if expected.replace(" ", "") == actual.replace(" ", ""):
        return "疑似空格增删"
    return "内容不同，可能是错位或误改原文"


def load_ir(ir_dir: Path) -> dict[str, dict[int, dict[str, Any]]]:
    """Group text entries by src_id (§2.3 merged library).

    Entries without a src_id land in the ANY_SRC group, which keeps single-source
    libraries working. A duplicate idx inside one group is corruption, not an
    overwrite to tolerate -- the old flat-table version hid exactly that.
    """
    path = ir_dir / "text_entries.jsonl"
    if not path.exists():
        raise Reject("IR_MISSING", f"找不到 {path}")
    groups: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise Reject("IR_CORRUPT", f"{path}:{lineno} 不是合法 JSON：{exc}")
            src = str(obj.get("src_id", ANY_SRC))
            idx = int(obj["idx"])
            if idx in groups[src]:
                raise Reject("IR_CORRUPT",
                             f"{path}:{lineno} src_id={src} 中 idx={idx} 重复")
            groups[src][idx] = obj
    return dict(groups)


def load_manifest(ir_dir: Path) -> dict[str, str]:
    """Map src_sha256 -> src_id from manifest.jsonl.

    Empty when there is no manifest; callers then fall back to ANY_SRC.
    """
    path = ir_dir / "manifest.jsonl"
    if not path.exists():
        return {}
    by_hash: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise Reject("IR_CORRUPT", f"{path}:{lineno} 不是合法 JSON：{exc}")
            digest = obj.get("sha256") or obj.get("src_sha256")
            if digest:
                by_hash[str(digest).lower()] = str(obj.get("src_id", ANY_SRC))
    return by_hash


def resolve_source(hdr_hash: str, manifest: dict[str, str],
                   ir: dict[str, dict[int, dict[str, Any]]]) -> str:
    """Pick the IR group this text file belongs to, by its header hash.

    A text file whose hash is absent from the manifest is rejected: that is the
    "imported an old dump" case §4.6 requires the hash for. Matching it against
    an arbitrary group would defeat the check.
    """
    if manifest:
        src = manifest.get(hdr_hash.lower())
        if src is None:
            raise Reject("SRC_HASH_MISMATCH",
                         f"文件头 src_sha256={hdr_hash[:16]}… 不对应 manifest 中的任何源；"
                         f"这份文件可能对应旧的 dump")
        if src not in ir:
            raise Reject("IR_MISSING", f"src_id={src} 在 text_entries.jsonl 中无记录")
        return src
    if len(ir) == 1:
        return next(iter(ir))
    raise Reject("IR_MISSING",
                 f"IR 含 {len(ir)} 个源但缺 manifest.jsonl，无法判定本文件对应哪个源")


def check_file(path: Path, ir: dict[str, dict[int, dict[str, Any]]],
               manifest: dict[str, str], idx_width: int) -> dict[str, Any]:
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig") if raw.startswith(b"\xef\xbb\xbf") else raw.decode("utf-8")
    lines = text.splitlines()
    hdr = parse_header(lines)

    src_id = resolve_source(hdr["src_sha256"], manifest, ir)
    entries = ir[src_id]
    target_codec = hdr["encoding"]["target"]
    seen: dict[int, int] = {}
    changed = 0
    i = 4
    pending_meta: dict[str, str] = {}
    pending_meta_line = 0

    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("#"):
            pending_meta = meta_of(line)
            pending_meta_line = i + 1
            i += 1
            continue

        mo = ORIG_RE.match(line)
        if not mo:
            if TRAN_RE.match(line):
                raise Reject("ORPHAN_TRANSLATION",
                             f"第 {i+1} 行是译文行但缺少配对的原文行")
            if PLACEHOLDER_LOOSE_RE.search(line) or line[:1] in (ORIG_MARK, TRAN_MARK):
                raise Reject("SEPARATOR_MIXED",
                             f"第 {i+1} 行分隔符混用或格式非法：{line[:60]!r}")
            raise Reject("LINE_FORMAT", f"第 {i+1} 行格式不合法：{line[:60]!r}")
        if i + 1 >= len(lines):
            raise Reject("MISSING_TRANSLATION", f"idx={mo.group('idx')} 缺少译文行")
        mt = TRAN_RE.match(lines[i + 1])
        if not mt:
            if ORIG_RE.match(lines[i + 1]):
                raise Reject("SEPARATOR_MIXED",
                             f"第 {i+2} 行本该是译文行（{TRAN_MARK}）却用了原文标记（{ORIG_MARK}）")
            raise Reject("LINE_FORMAT", f"第 {i+2} 行不是合法译文行：{lines[i+1][:60]!r}")

        if mo.group("idx") != mt.group("idx"):
            raise Reject("IDX_MISMATCH",
                         f"第 {i+1}-{i+2} 行编号不一致：{mo.group('idx')} != {mt.group('idx')}")
        if len(mo.group("idx")) != len(mt.group("idx")):
            raise Reject("IDX_WIDTH", f"第 {i+1}-{i+2} 行 idx 宽度不一致（须定宽）")
        if len(mo.group("idx")) != idx_width:
            raise Reject("IDX_WIDTH",
                         f"第 {i+1} 行 idx 宽度为 {len(mo.group('idx'))}，须定宽 {idx_width} 位"
                         f"（§4.6）：{mo.group('idx')!r}")
        idx = int(mo.group("idx"))
        if mo.group("tag") != mt.group("tag"):
            raise Reject("TAG_MISMATCH",
                         f"idx={idx} 标签不一致：{mo.group('tag')!r} != {mt.group('tag')!r}", idx=idx)
        tag = mo.group("tag")
        if tag not in CORE_TAGS:
            raise Reject("TAG_UNKNOWN", f"idx={idx} tag={tag!r} 不在闭集 {sorted(CORE_TAGS)}", idx=idx)
        if idx in seen:
            raise Reject("IDX_DUPLICATE", f"idx={idx} 重复出现（第 {seen[idx]} 行与第 {i+1} 行）", idx=idx)
        seen[idx] = i + 1

        entry = entries.get(idx)
        if entry is None:
            raise Reject("IDX_UNKNOWN", f"idx={idx} 不存在于 IR（src_id={src_id}）", idx=idx)

        # The metadata comment must describe the pair that follows it. Without this
        # check, swapping two whole blocks leaves every pair internally consistent
        # while silently pairing each entry with the previous block's policy/tag.
        if pending_meta:
            meta_idx = pending_meta.get("idx")
            if meta_idx is not None and int(meta_idx) != idx:
                raise Reject("META_DESYNC",
                             f"第 {pending_meta_line} 行注释声明 idx={int(meta_idx)}，"
                             f"但紧随的条目是 idx={idx}；疑似整块被交换或注释错位", idx=idx)
            meta_tag = pending_meta.get("tag")
            if meta_tag is not None and meta_tag != tag:
                raise Reject("META_DESYNC",
                             f"idx={idx} 注释声明 tag={meta_tag!r}，行内是 {tag!r}", idx=idx)

        expected_src = entry.get("source", "")
        if mo.group("text") != expected_src:
            raise Reject(
                "SOURCE_ANCHOR",
                f"idx={idx} 原文行与 IR 不一致（{diagnose_source_mismatch(expected_src, mo.group('text'))}）\n"
                f"    IR  : {expected_src[:100]!r}\n"
                f"    文件: {mo.group('text')[:100]!r}",
                idx=idx)

        policy = pending_meta.get("policy") or entry.get("translate_policy", "translatable")
        pending_meta = {}
        if policy not in POLICIES:
            raise Reject("POLICY_UNKNOWN", f"idx={idx} policy={policy!r} 非法", idx=idx)
        dst = mt.group("text")

        # §4.6: export pre-fills the translation with the source, so an empty
        # line means the content was deleted. Treating it as "untranslated"
        # writes an empty string back into the target file. "Untranslated" is
        # target == source, never empty.
        if not dst:
            raise Reject("EMPTY_TRANSLATION",
                         f"idx={idx} 译文行为空；导出时已预填原文，空行表示内容被误删"
                         f"（未翻译的判据是译文等于原文，不是留空）", idx=idx)

        if policy == "frozen" and dst != expected_src:
            raise Reject("FROZEN_MODIFIED",
                         f"idx={idx} 标记 frozen 但译文行被改动；原样保留或改 IR 中的策略", idx=idx)

        if dst != expected_src:
            changed += 1
            check_placeholders(idx, mo.group("text"), dst)
            try:
                nbytes = visible_len_bytes(dst, target_codec)
            except (UnicodeEncodeError, LookupError) as exc:
                bad = getattr(exc, "object", ["?"])[getattr(exc, "start", 0)] if isinstance(exc, UnicodeEncodeError) else "?"
                cands = [c for c in ("utf-8", "gbk", "big5", "cp932", "cp949")
                         if c != target_codec and _can_encode(bad, c)]
                raise Reject("ENCODING_UNREPRESENTABLE",
                             f"idx={idx} 编码 {target_codec} 无法表示 {bad!r}"
                             + (f"；可改用 {', '.join(cands)}" if cands else ""), idx=idx)
            cap = entry.get("slot_capacity")
            if policy == "length-locked":
                orig = entry.get("raw_len")
                if orig is not None and nbytes != orig:
                    raise Reject("LENGTH_LOCKED",
                                 f"idx={idx} 要求等长：原 {orig} 字节，译文 {nbytes} 字节", idx=idx)
            elif cap is not None and nbytes > cap:
                raise Reject("LENGTH_OVERFLOW",
                             f"idx={idx} 译文超长 {nbytes - cap} 字节"
                             f"（原文占 {cap} 字节，译文需 {nbytes} 字节）", idx=idx)
        i += 2

    scope = hdr["scope"]
    if scope["part_total"] == 1 and scope["kind"] == "all":
        missing = sorted(set(entries) - set(seen))
        if missing:
            raise Reject("INCOMPLETE",
                         f"缺少 {len(missing)} 条；第一条缺失 idx={missing[0]}")
    return {"file": str(path), "src_id": src_id,
            "entries": len(seen), "changed": changed,
            "part": f"{scope['part_index']}/{scope['part_total']}",
            "target_encoding": target_codec}


def _can_encode(ch: str, codec: str) -> bool:
    try:
        ch.encode(codec)
        return True
    except (UnicodeEncodeError, LookupError):
        return False


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("ir_dir", type=Path, help="IR 目录（含 text_entries.jsonl）")
    ap.add_argument("texts", type=Path, nargs="+", help="双行文本文件或目录")
    ap.add_argument("--idx-width", type=int, default=IDX_WIDTH,
                    help=f"idx 定宽位数（默认 {IDX_WIDTH}，§4.6）")
    ap.add_argument("--report", type=Path)
    args = ap.parse_args(list(argv) if argv is not None else None)

    files: list[Path] = []
    for t in args.texts:
        files.extend(sorted(t.rglob("*.txt")) if t.is_dir() else [t])

    result: dict[str, Any] = {"ok": True, "files": [], "errors": []}
    try:
        ir = load_ir(args.ir_dir)
        manifest = load_manifest(args.ir_dir)
    except Reject as exc:
        result = {"ok": False, "files": [], "errors": [{"code": exc.code, "detail": exc.detail}]}
        _emit(result, args.report)
        return 1

    # Shards are counted per source: two sources each split into 2 parts must not
    # combine into one "complete" set of 4.
    parts: dict[tuple[str, int], set[int]] = defaultdict(set)
    for f in files:
        try:
            info = check_file(f, ir, manifest, args.idx_width)
            result["files"].append(info)
            k, n = (int(x) for x in info["part"].split("/"))
            parts[(info["src_id"], n)].add(k)
        except Reject as exc:
            result["ok"] = False
            result["errors"].append({"file": str(f), "code": exc.code,
                                     "detail": exc.detail, **exc.ctx})
        except (OSError, UnicodeDecodeError) as exc:
            result["ok"] = False
            result["errors"].append({"file": str(f), "code": "UNREADABLE", "detail": str(exc)})

    for (src_id, total), got in sorted(parts.items()):
        if total > 1 and len(got) != total:
            result["ok"] = False
            result["errors"].append({
                "code": "SHARD_INCOMPLETE", "src_id": src_id,
                "detail": f"src_id={src_id} 分片不完整：共 {total} 片，"
                          f"缺 {sorted(set(range(1, total+1)) - got)}"})

    _emit(result, args.report)
    return 0 if result["ok"] else 1


def _emit(result: dict[str, Any], report: Path | None) -> None:
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if report:
        report.write_text(text, encoding="utf-8")
    write_stdout(text)

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
