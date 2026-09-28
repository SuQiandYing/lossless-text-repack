#!/usr/bin/env python3
"""Validate TEXT/1 and TEXT/2 projections against a trusted IR snapshot.

IR: text_entries.jsonl has idx, source, tag, translate_policy and optional
src_id, raw_len, slot_capacity. Manifest rows bind src_id to sha256. Editable
comments never grant permissions. `idx-range range=START-END part=1/1` requires
--expected-scope JSON supplied by the caller (src_id -> integer idx array).
Without that trusted scope, submitted sources must be complete.
--target-encoding binds all submitted headers to the caller's trusted codec.
Without it, encoding_binding=not_verified: a pass only checks representability
in the header-declared codec, not agreement with a repack job configuration.
Exit 0=pass, 1=fail (invalid input), 2=not_verified (missing evidence).
Never mutates any input. A pass is import validation, not a round-trip proof.
"""
from __future__ import annotations

import argparse
import codecs
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

ORIG_MARK, TRAN_MARK = "○", "●"
IDX_WIDTH = 8
ANY_SRC = "*"
ORIG_RE = re.compile(r"^○(?P<idx>[0-9]+)○(?P<tag>[a-z_]+)○(?P<text>.*)$")
TRAN_RE = re.compile(r"^●(?P<idx>[0-9]+)●(?P<tag>[a-z_]+)●(?P<text>.*)$")
PLACEHOLDER_RE = re.compile(r"\{\{[0-9A-F]{2}(?::[0-9A-F]{2})*\}\}")
CORE_TAGS = {"name", "msg", "choice", "label", "ui", "system", "ruby", "misc"}
POLICIES = {"translatable", "length-locked", "review-required", "frozen"}
HASH_RE = re.compile(r"[0-9a-fA-F]{64}")


class Reject(Exception):
    def __init__(self, code: str, detail: str, **ctx: Any) -> None:
        super().__init__(detail)
        self.code, self.detail, self.ctx = code, detail, ctx


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise Reject("CLI_ARGUMENTS", message)


def integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not (isinstance(value, int) or
            isinstance(value, str) and re.fullmatch(r"[0-9]+", value)):
        raise Reject("SCHEMA", f"{label} must be a non-negative integer")
    try:
        out = int(value)
    except ValueError as exc:
        raise Reject("SCHEMA", f"{label}: integer too large to parse") from exc
    if out < 0:
        raise Reject("SCHEMA", f"{label} must be non-negative")
    return out


def json_rows(path: Path) -> list[dict[str, Any]]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError(f"duplicate JSON field {key}")
            obj[key] = value
        return obj

    def invalid_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant {value}")

    rows = []
    for n, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            obj = json.loads(raw, object_pairs_hook=unique_object, parse_constant=invalid_constant)
        except (ValueError, RecursionError) as exc:
            raise Reject("IR_CORRUPT", f"{path}:{n}: {exc}") from exc
        if not isinstance(obj, dict):
            raise Reject("SCHEMA", f"{path}:{n}: expected JSON object")
        rows.append(obj)
    return rows


def meta_of(comment: str) -> dict[str, str]:
    pairs = re.findall(r"([a-zA-Z_][\w]*)=([^\s]+)", comment)
    out: dict[str, str] = {}
    for key, value in pairs:
        if key in out:
            raise Reject("DUPLICATE_FIELD", f"duplicate field {key}")
        out[key] = value
    return out


def parse_header(lines: list[str]) -> dict[str, Any]:
    if len(lines) < 4:
        raise Reject("HEADER_TRUNCATED", "TEXT/2 header requires four lines")
    version = re.match(r"^#\s+TEXT/([12])\s+", lines[0])
    if not version:
        raise Reject("HEADER_VERSION", "supported formats are TEXT/1 and TEXT/2")
    hdr: dict[str, Any] = meta_of(lines[0])
    hdr["format_version"] = int(version[1])
    for key in ("ir", "tool", "src_sha256"):
        if key not in hdr:
            raise Reject("HEADER_FIELD", f"missing {key}")
    if not HASH_RE.fullmatch(hdr["src_sha256"]):
        raise Reject("HEADER_HASH", "src_sha256 must be 64 hexadecimal characters")
    if not lines[1].startswith("# encoding "):
        raise Reject("HEADER_LINE2", "expected # encoding")
    enc = meta_of(lines[1])
    for key in ("source", "target", "file"):
        if key not in enc:
            raise Reject("HEADER_FIELD", f"missing encoding {key}")
        try:
            codecs.lookup(enc[key])
        except LookupError as exc:
            raise Reject("ENCODING_UNKNOWN", f"unknown {key} codec {enc[key]!r}") from exc
    if codecs.lookup(enc["file"]).name not in {"utf-8", "utf-8-sig"}:
        raise Reject("FILE_ENCODING", "TEXT/2 files must be UTF-8")
    hdr["encoding"] = enc
    if not lines[2].startswith("# scope "):
        raise Reject("HEADER_LINE3", "expected # scope")
    scope: dict[str, Any] = meta_of(lines[2])
    if hdr["format_version"] == 1 and scope.get("kind") in {"all", "partition"}:
        scope.setdefault("range", "ALL")
    if scope.get("kind") not in {"all", "idx-range", "partition"}:
        raise Reject("SCOPE_KIND", "scope kind must be all, idx-range or partition")
    match = re.fullmatch(r"([0-9]+)/([0-9]+)", scope.get("part", ""))
    if not match:
        raise Reject("SCOPE_PART", "part=K/N is required")
    k, n = map(int, match.groups())
    if not 1 <= k <= n:
        raise Reject("SCOPE_PART", "part must satisfy 1 <= K <= N")
    scope.update(part_index=k, part_total=n)
    if scope.get("range") == "ALL":
        if scope["kind"] == "idx-range":
            raise Reject("SCOPE_RANGE", "idx-range requires START-END (inclusive)")
        scope["bounds"] = None
    else:
        match = re.fullmatch(r"([0-9]+)-([0-9]+)", scope.get("range", ""))
        if not match or int(match[1]) > int(match[2]):
            raise Reject("SCOPE_RANGE", "range must be ALL or START-END (inclusive)")
        if scope["kind"] == "all":
            raise Reject("SCOPE_RANGE", "kind=all requires range=ALL")
        scope["bounds"] = [int(match[1]), int(match[2])]
    if not lines[3].startswith("# tags "):
        raise Reject("HEADER_LINE4", "expected # tags")
    tags = lines[3].split()[2:]
    if not tags or len(tags) != len(set(tags)) or not set(tags) <= CORE_TAGS:
        raise Reject("HEADER_TAGS", "tags must be a nonempty unique subset of the closed tag set")
    hdr["tags"] = tags
    hdr["scope"] = scope
    return hdr


def load_ir(ir_dir: Path) -> dict[str, dict[int, dict[str, Any]]]:
    groups: dict[str, dict[int, dict[str, Any]]] = defaultdict(dict)
    for row in json_rows(ir_dir / "text_entries.jsonl"):
        idx = integer(row.get("idx"), "idx")
        src = row.get("src_id", ANY_SRC)
        if not isinstance(src, str) or not src:
            raise Reject("SCHEMA", "src_id must be a nonempty string")
        if not isinstance(row.get("source"), str):
            raise Reject("SCHEMA", f"idx={idx}: source must be a string")
        if not isinstance(row.get("tag"), str) or row["tag"] not in CORE_TAGS:
            raise Reject("SCHEMA", f"idx={idx}: trusted IR tag is missing or invalid")
        if not isinstance(row.get("translate_policy"), str) or row["translate_policy"] not in POLICIES:
            raise Reject("SCHEMA", f"idx={idx}: trusted IR translate_policy is missing or invalid")
        for field in ("raw_len", "slot_capacity"):
            if row.get(field) is not None:
                row[field] = integer(row[field], field)
        if row["translate_policy"] == "length-locked" and row.get("raw_len") is None:
            raise Reject("SCHEMA", f"idx={idx}: length-locked requires raw_len")
        if idx in groups[src]:
            raise Reject("IR_CORRUPT", f"duplicate src_id={src}, idx={idx}")
        groups[src][idx] = row
    if not groups:
        raise Reject("EMPTY_IR", "text_entries.jsonl contains no entries")
    return dict(groups)


def load_manifest(ir_dir: Path) -> dict[str, list[str]]:
    path = ir_dir / "manifest.jsonl"
    if not path.exists():
        return {}
    by_hash: dict[str, list[str]] = defaultdict(list)
    seen: set[str] = set()
    for row in json_rows(path):
        digest = row.get("sha256", row.get("src_sha256"))
        src = row.get("src_id", ANY_SRC)
        if not isinstance(digest, str) or not HASH_RE.fullmatch(digest):
            raise Reject("SCHEMA", "manifest requires a valid sha256")
        if not isinstance(src, str) or not src or src in seen:
            raise Reject("SCHEMA", "manifest src_id must be unique nonempty strings")
        if "sha256" in row and "src_sha256" in row:
            alias = row["src_sha256"]
            if not isinstance(alias, str) or row["sha256"].lower() != alias.lower():
                raise Reject("SCHEMA", "conflicting manifest hash fields")
        seen.add(src)
        by_hash[digest.lower()].append(src)
    if not by_hash:
        raise Reject("EMPTY_MANIFEST", "manifest exists but contains no sources")
    return dict(by_hash)


def load_expected_scope(path: Path | None, ir: dict[str, dict[int, dict[str, Any]]]) -> dict[str, set[int]]:
    if path is None:
        return {}
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate source {key}")
            result[key] = value
        return result
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object)
    except (ValueError, RecursionError) as exc:
        raise Reject("SCOPE_SCHEMA", f"invalid --expected-scope JSON: {exc}") from exc
    if not isinstance(raw, dict) or not raw:
        raise Reject("SCOPE_SCHEMA", "expected scope must be a nonempty src_id -> idx array object")
    result = {}
    for src, values in raw.items():
        if src not in ir or not isinstance(values, list) or not values:
            raise Reject("SCOPE_SCHEMA", f"src_id={src}: unknown source or missing idx array")
        indices = [integer(value, "expected-scope idx") for value in values]
        if len(indices) != len(set(indices)) or not set(indices) <= set(ir[src]):
            raise Reject("SCOPE_SCHEMA", f"src_id={src}: duplicate or unknown expected idx")
        result[src] = set(indices)
    return result


def resolve_source(hdr_hash: str, manifest: dict[str, list[str]],
                   ir: dict[str, dict[int, dict[str, Any]]],
                   declared_src: str | None = None) -> str:
    if manifest:
        candidates = manifest.get(hdr_hash.lower(), [])
        if declared_src is not None:
            candidates = [src for src in candidates if src == declared_src]
        if len(candidates) != 1:
            raise Reject("SRC_HASH_MISMATCH", "source hash/src_id is absent or ambiguous in manifest")
        src = candidates[0]
        if src not in ir:
            raise Reject("IR_MISSING", f"src_id={src} has no text entries")
        return src
    if len(ir) == 1 and (declared_src is None or declared_src in ir):
        return next(iter(ir))  # Caller reports missing hash evidence as not_verified.
    raise Reject("IR_MISSING", "cannot route multiple IR sources without a manifest")


def placeholder_tokens(text: str) -> list[str]:
    tokens = PLACEHOLDER_RE.findall(text)
    residue = PLACEHOLDER_RE.sub("", text)
    if "{{" in residue or "}}" in residue:
        raise Reject("PLACEHOLDER_BROKEN", "malformed/unbalanced raw-byte placeholder")
    return tokens


def placeholder_bytes(text: str) -> list[int]:
    return [int(b, 16) for token in placeholder_tokens(text) for b in token[2:-2].split(":")]


def check_placeholders(idx: int, src: str, dst: str) -> None:
    if placeholder_tokens(src) != placeholder_tokens(dst):
        raise Reject("PLACEHOLDER_BROKEN", f"idx={idx}: placeholder grouping/order/bytes changed", idx=idx)


def visible_len_bytes(text: str, codec: str) -> int:
    total, pos = 0, 0
    for match in PLACEHOLDER_RE.finditer(text):
        total += len(text[pos:match.start()].encode(codec, errors="strict"))
        total += len(match[0][2:-2].split(":"))
        pos = match.end()
    return total + len(text[pos:].encode(codec, errors="strict"))


def diagnose_source_mismatch(expected: str, actual: str) -> str:
    if unicodedata.normalize("NFKC", expected) == unicodedata.normalize("NFKC", actual):
        return "compatibility/full-width normalization detected"
    return "source anchor differs from trusted IR"


def check_file(path: Path, ir: dict[str, dict[int, dict[str, Any]]],
               manifest: dict[str, list[str]], idx_width: int,
               expected_scope: dict[str, set[int]] | None = None,
               expected_codec: str | None = None) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    hdr = parse_header(lines)
    src_id = resolve_source(hdr["src_sha256"], manifest, ir, hdr.get("src_id"))
    entries, seen = ir[src_id], set()
    target_codec = hdr["encoding"]["target"]
    canonical_codec = codecs.lookup(target_codec).name
    if expected_codec is not None and canonical_codec != expected_codec:
        raise Reject("TARGET_ENCODING_MISMATCH", f"header target codec {canonical_codec!r} differs from caller-owned codec {expected_codec!r}")
    scope = hdr["scope"]
    authorized = (expected_scope or {}).get(src_id)
    if scope["kind"] == "idx-range" and authorized is None:
        raise Reject("SCOPE_NOT_AUTHORIZED", "idx-range requires caller-owned --expected-scope; the editable header cannot reduce completeness")
    if authorized is not None and authorized != set(entries) and scope["kind"] != "idx-range":
        raise Reject("SCOPE_MISMATCH", "a partial expected scope requires an idx-range projection")
    changed, i = 0, 4
    pending: dict[str, str] = {}
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith("#"):
            parsed = meta_of(line)
            for key, value in parsed.items():
                if key in pending:
                    raise Reject("META_DESYNC", f"metadata {key} repeated before a text pair")
                pending[key] = value
            i += 1
            continue
        mo = ORIG_RE.fullmatch(line)
        mt = TRAN_RE.fullmatch(lines[i + 1]) if i + 1 < len(lines) else None
        if not mo or not mt:
            raise Reject("LINE_FORMAT", f"line {i + 1}: expected consecutive original/translation pair")
        if mo["idx"] != mt["idx"]:
            raise Reject("IDX_MISMATCH", f"line {i + 1}: original/translation idx differ")
        if len(mo["idx"]) != idx_width:
            raise Reject("IDX_WIDTH", f"idx requires {idx_width} ASCII decimal digits")
        idx = int(mo["idx"])
        if idx in seen:
            raise Reject("IDX_DUPLICATE", f"idx={idx} repeated")
        seen.add(idx)
        if idx not in entries:
            raise Reject("IDX_UNKNOWN", f"idx={idx} absent from source {src_id}")
        entry = entries[idx]
        if mo["tag"] not in hdr["tags"]:
            raise Reject("TAG_UNDECLARED", f"idx={idx}: tag not listed in header")
        if mo["tag"] != mt["tag"] or mo["tag"] != entry["tag"]:
            raise Reject("TAG_MISMATCH", f"idx={idx}: tag must match trusted IR")
        if "idx" in pending and (not re.fullmatch(r"[0-9]{" + str(idx_width) + r"}", pending["idx"]) or int(pending["idx"]) != idx):
            raise Reject("META_DESYNC", f"idx={idx}: metadata idx/width mismatch")
        if "tag" in pending and pending["tag"] != entry["tag"]:
            raise Reject("META_DESYNC", f"idx={idx}: metadata tag mismatch")
        policy = entry["translate_policy"]
        if "policy" in pending and pending["policy"] != policy:
            raise Reject("POLICY_MISMATCH", f"idx={idx}: editable metadata cannot override trusted IR policy")
        for field in ("off", "inst"):
            if field in pending:
                if field not in entry:
                    raise Reject("META_UNVERIFIABLE", f"idx={idx}: metadata {field} has no IR anchor")
                if str(entry[field]) != pending[field]:
                    # Numeric offsets permit a hexadecimal display of an integer IR value.
                    try:
                        equal = int(str(entry[field]), 0) == int(pending[field], 0)
                    except ValueError:
                        equal = False
                    if not equal:
                        raise Reject("META_DESYNC", f"idx={idx}: metadata {field} mismatch")
        src, dst = entry["source"], mt["text"]
        if mo["text"] != src:
            raise Reject("SOURCE_ANCHOR", f"idx={idx}: {diagnose_source_mismatch(src, mo['text'])}")
        if not dst and src:
            raise Reject("EMPTY_TRANSLATION", f"idx={idx}: empty translation deletes nonempty source")
        check_placeholders(idx, src, dst)
        if dst != src:
            changed += 1
            if policy == "frozen":
                raise Reject("FROZEN_MODIFIED", f"idx={idx}: frozen entry changed")
            if policy == "review-required" and pending.get("reviewed") != "true":
                raise Reject("REVIEW_REQUIRED", f"idx={idx}: changed entry requires reviewed=true")
            try:
                nbytes = visible_len_bytes(dst, target_codec)
            except (UnicodeEncodeError, LookupError) as exc:
                raise Reject("ENCODING_UNREPRESENTABLE", f"idx={idx}: {exc}") from exc
            if policy == "length-locked" and nbytes != entry["raw_len"]:
                raise Reject("LENGTH_LOCKED", f"idx={idx}: expected {entry['raw_len']} bytes, got {nbytes}")
            if entry.get("slot_capacity") is not None and nbytes > entry["slot_capacity"]:
                raise Reject("LENGTH_OVERFLOW", f"idx={idx}: {nbytes} exceeds slot capacity {entry['slot_capacity']}")
        pending = {}
        i += 2
    if pending:
        raise Reject("ORPHAN_METADATA", "trailing metadata has no text pair")
    if not seen:
        raise Reject("EMPTY_TEXT", "no text pairs in input")
    bounds = scope["bounds"]
    if bounds and any(not bounds[0] <= idx <= bounds[1] for idx in seen):
        raise Reject("SCOPE_RANGE", "entry lies outside declared idx range")
    allowed = set(entries) if authorized is None else authorized
    if not seen <= allowed:
        raise Reject("SCOPE_MISMATCH", "input contains indices outside caller-owned expected scope")
    expected = {idx for idx in allowed if not bounds or bounds[0] <= idx <= bounds[1]}
    if scope["part_total"] == 1 and seen != expected:
        raise Reject("INCOMPLETE", f"missing declared entries: {sorted(expected - seen)[:20]}")
    return {"file": str(path), "src_id": src_id, "entries": len(seen), "changed": changed,
            "format_version": hdr["format_version"], "legacy_format": hdr["format_version"] == 1,
            "indices": sorted(seen), "scope": scope,
            "part": f"{scope['part_index']}/{scope['part_total']}",
            "target_encoding": target_codec, "canonical_target_encoding": canonical_codec,
            "encoding_binding": "verified" if expected_codec is not None else "not_verified",
            "source_hash_verified": bool(manifest)}


def check_shards(infos: list[dict[str, Any]], ir: dict[str, dict[int, dict[str, Any]]],
                 expected_scope: dict[str, set[int]] | None = None) -> None:
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for info in infos:
        by_source[info["src_id"]].append(info)
    if set(expected_scope or {}) - set(by_source):
        raise Reject("SCOPE_INCOMPLETE", "one or more sources required by --expected-scope have no input")
    for src_id, group in by_source.items():
        indices: set[int] = set()
        parts: set[int] = set()
        totals = {info["scope"]["part_total"] for info in group}
        kinds = {info["scope"]["kind"] for info in group}
        if len(totals) != 1 or len(kinds) != 1:
            raise Reject("SHARD_SCOPE_MISMATCH", f"src_id={src_id}: inconsistent shard kind/total")
        total, kind = next(iter(totals)), next(iter(kinds))
        declared_scope: set[int] = set()
        for info in group:
            current = set(info["indices"])
            if indices & current:
                raise Reject("SHARD_IDX_DUPLICATE", f"src_id={src_id}: duplicate indices across input files")
            indices |= current
            part = info["scope"]["part_index"]
            if part in parts and (total > 1 or kind != "idx-range"):
                raise Reject("SHARD_DUPLICATE", f"src_id={src_id}: duplicate part {part}")
            parts.add(part)
            bounds = info["scope"]["bounds"]
            declared_scope |= {idx for idx in ir[src_id] if not bounds or bounds[0] <= idx <= bounds[1]}
        if total > 1 and parts != set(range(1, total + 1)):
            raise Reject("SHARD_INCOMPLETE", f"src_id={src_id}: missing shards")
        expected = (expected_scope or {}).get(src_id, set(ir[src_id]))
        if indices != expected:
            raise Reject("INCOMPLETE", f"src_id={src_id}: missing declared indices {sorted(expected - indices)[:20]}")
        if kind == "idx-range" and declared_scope != expected:
            raise Reject("SCOPE_MISMATCH", f"src_id={src_id}: header ranges differ from caller-owned expected scope")


def main(argv: Iterable[str] | None = None) -> int:
    ap = Parser(description=__doc__)
    ap.add_argument("ir_dir", type=Path)
    ap.add_argument("texts", type=Path, nargs="+")
    ap.add_argument("--idx-width", type=int, default=IDX_WIDTH)
    ap.add_argument("--target-encoding", help="caller-owned expected target codec for this job; headers must name the same canonical codec")
    ap.add_argument("--expected-scope", type=Path, help="caller-owned JSON object mapping src_id to the exact expected idx array; required for partial import")
    ap.add_argument("--report", type=Path)
    try:
        args = ap.parse_args(list(argv) if argv is not None else None)
    except Reject as exc:
        _emit({"ok": False, "status": "fail", "files": [], "errors": [{"code": exc.code, "detail": exc.detail}]}, None)
        return 1
    result: dict[str, Any] = {"ok": False, "status": "fail", "files": [], "errors": [],
                              "verification_scope": "submitted-sources-and-declared-ranges",
                              "encoding_binding": "not_verified",
                              "encoding_verification_scope": "header-declared-codec-representability"}
    manifest: dict[str, list[str]] = {}
    try:
        if not 1 <= args.idx_width <= 32:
            raise Reject("IDX_WIDTH", "--idx-width must be between 1 and 32")
        expected_codec = None
        if args.target_encoding is not None:
            try:
                expected_codec = codecs.lookup(args.target_encoding).name
            except LookupError as exc:
                raise Reject("ENCODING_UNKNOWN", f"unknown caller-owned target codec {args.target_encoding!r}") from exc
            result["expected_target_encoding"] = expected_codec
        files = []
        for path in args.texts:
            files.extend(sorted(path.rglob("*.txt")) if path.is_dir() else [path])
        protected = [args.ir_dir / "text_entries.jsonl", args.ir_dir / "manifest.jsonl", *files]
        if args.expected_scope:
            protected.append(args.expected_scope)
        if args.report and args.report.resolve() in {path.resolve() for path in protected}:
            args.report = None
            raise Reject("INPUT_REPORT_COLLISION", "--report must not overwrite an input")
        if not files:
            raise Reject("NO_INPUT", "no .txt input files found")
        if len({path.resolve() for path in files}) != len(files):
            raise Reject("DUPLICATE_INPUT", "same input path supplied more than once")
        ir, manifest = load_ir(args.ir_dir), load_manifest(args.ir_dir)
        expected_scope = load_expected_scope(args.expected_scope, ir)
        for path in files:
            try:
                result["files"].append(check_file(path, ir, manifest, args.idx_width, expected_scope, expected_codec))
            except Reject as exc:
                result["errors"].append({"file": str(path), "code": exc.code, "detail": exc.detail, **exc.ctx})
            except (OSError, UnicodeError) as exc:
                result["errors"].append({"file": str(path), "code": "UNREADABLE", "detail": str(exc)})
        if not result["errors"]:
            check_shards(result["files"], ir, expected_scope)
            if expected_codec is not None:
                result["encoding_binding"] = "verified"
                result["encoding_verification_scope"] = "caller-owned-codec-binding-and-representability"
    except Reject as exc:
        result["errors"].append({"code": exc.code, "detail": exc.detail, **exc.ctx})
    except (OSError, UnicodeError) as exc:
        result["errors"].append({"code": "UNREADABLE", "detail": str(exc)})
    if not result["errors"]:
        result["status"] = "pass" if manifest else "not_verified"
        if not manifest:
            result["not_verified"] = [{"code": "SOURCE_HASH_UNVERIFIED", "detail": "manifest.jsonl is missing; source binding was not proved"}]
    result["ok"] = result["status"] == "pass"
    try:
        _emit(result, args.report)
    except OSError as exc:
        result.update(ok=False, status="fail")
        result["errors"].append({"code": "REPORT_IO_ERROR", "detail": str(exc)})
        _emit(result, None)
    return {"pass": 0, "fail": 1, "not_verified": 2}[result["status"]]


def _emit(result: dict[str, Any], report: Path | None) -> None:
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if report:
        report.write_text(text, encoding="utf-8")
    write_stdout(text)


def write_stdout(text: str) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="strict")
    except (AttributeError, OSError):
        pass
    sys.stdout.write(text)


if __name__ == "__main__":
    raise SystemExit(main())
