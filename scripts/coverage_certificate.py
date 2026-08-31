#!/usr/bin/env python3
"""Validate a byte-coverage certificate against a local source file."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

STATUSES = {
    "decoded",
    "structured-unknown",
    "unknown_opaque_block",
    "opaque-preserved",
    "padding",
    "proven-gap",
}
ANALYSIS_MODES = {
    "host-disasm",
    "bytecode-disasm",
    "mixed-disasm",
    "data-text-only",
}
UNPACK_MODES = {
    "not-required",
    "targeted",
    "full",
    "blocked",
    "skipped-by-plan",
}
TEXT_SOURCES = {"external", "embedded", "absent", "unknown"}
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def load_json(path: Path) -> dict[str, Any]:
    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle, object_pairs_hook=reject_duplicate)
    if not isinstance(value, dict):
        raise ValueError("certificate root must be an object")
    return value


def stream_sha256(path: Path, start: int, end: int) -> str:
    digest = hashlib.sha256()
    remaining = end - start
    with path.open("rb") as handle:
        handle.seek(start)
        while remaining:
            block = handle.read(min(1024 * 1024, remaining))
            if not block:
                raise ValueError("source ended while hashing interval")
            digest.update(block)
            remaining -= len(block)
    return digest.hexdigest()


def integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    return value


def validate_decision_fields(certificate: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate optional case-decision fields without breaking legacy certificates."""
    errors: list[dict[str, Any]] = []
    enum_fields = {
        "analysis_mode": ANALYSIS_MODES,
        "unpack_mode": UNPACK_MODES,
        "text_source": TEXT_SOURCES,
    }
    for field, allowed in enum_fields.items():
        value = certificate.get(field)
        if value is not None and value not in allowed:
            errors.append({"error": f"invalid {field}", "value": value})
    disasm_required = certificate.get("disasm_required")
    if disasm_required is not None and not isinstance(disasm_required, bool):
        errors.append({"error": "disasm_required must be boolean"})
    evidence_refs = certificate.get("decision_evidence_refs")
    if evidence_refs is not None and (
        not isinstance(evidence_refs, list)
        or any(not isinstance(item, str) or not item for item in evidence_refs)
    ):
        errors.append({"error": "decision_evidence_refs must be a list of non-empty strings"})
    instruction_coverage = certificate.get("instruction_coverage")
    if instruction_coverage is not None:
        if instruction_coverage != "not_applicable":
            if isinstance(instruction_coverage, bool):
                errors.append({"error": "instruction_coverage must not be boolean"})
            else:
                try:
                    ratio = float(instruction_coverage)
                except (TypeError, ValueError):
                    ratio = -1.0
                if not 0.0 <= ratio <= 1.0:
                    errors.append({"error": "instruction_coverage must be a ratio in [0, 1] or not_applicable"})
    return errors


def validate_intervals(certificate: dict[str, Any], source: Path) -> dict[str, Any]:
    source_size = integer(certificate.get("source_size"), "source_size")
    actual_size = source.stat().st_size
    if source_size != actual_size:
        raise ValueError(f"source_size {source_size} != file size {actual_size}")
    raw_intervals = certificate.get("intervals")
    if not isinstance(raw_intervals, list):
        raise ValueError("intervals must be a list")
    cursor = 0
    seen_ids: set[str] = set()
    counts = {status: 0 for status in STATUSES}
    covered = 0
    errors: list[dict[str, Any]] = validate_decision_fields(certificate)
    for index, item in enumerate(raw_intervals):
        if not isinstance(item, dict):
            errors.append({"index": index, "error": "interval must be an object"})
            continue
        interval_id = item.get("id")
        if not isinstance(interval_id, str) or not interval_id:
            errors.append({"index": index, "error": "missing id"})
        elif interval_id in seen_ids:
            errors.append({"index": index, "error": f"duplicate id {interval_id}"})
        else:
            seen_ids.add(interval_id)
        try:
            start = integer(item.get("start"), f"interval[{index}].start")
            end = integer(item.get("end"), f"interval[{index}].end")
            if start != cursor:
                kind = "gap" if start > cursor else "overlap"
                errors.append({"index": index, "error": kind, "expected": cursor, "actual": start})
            if start < 0 or end <= start or end > source_size:
                errors.append({"index": index, "error": "range out of bounds"})
            if end > cursor:
                covered += end - max(start, cursor)
                cursor = end
            status = item.get("status")
            if status not in STATUSES:
                errors.append({"index": index, "error": "unknown status", "status": status})
            else:
                interval_length = max(0, end - start)
                counts[status] += interval_length
                if status == "proven-gap":
                    errors.append({"index": index, "error": "proven-gap blocks strict success"})
            expected_hash = item.get("raw_sha256")
            if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash):
                errors.append({"index": index, "error": "raw_sha256 must be 64 hex characters"})
            elif 0 <= start <= end <= source_size:
                actual_hash = stream_sha256(source, start, end)
                if actual_hash.lower() != expected_hash.lower():
                    errors.append({"index": index, "error": "raw hash mismatch", "expected": expected_hash, "actual": actual_hash})
        except ValueError as exc:
            errors.append({"index": index, "error": str(exc)})
    if cursor != source_size:
        errors.append({"error": "final gap", "expected": source_size, "actual": cursor})
    gaps = certificate.get("gaps", [])
    overlaps = certificate.get("overlaps", [])
    if not isinstance(gaps, list) or not isinstance(overlaps, list):
        errors.append({"error": "gaps and overlaps must be lists"})
    elif gaps or overlaps:
        errors.append({"error": "certificate lists gaps or overlaps", "gaps": gaps, "overlaps": overlaps})
    recorded_counts = certificate.get("status_counts")
    if recorded_counts is not None:
        if not isinstance(recorded_counts, dict):
            errors.append({"error": "status_counts must be an object"})
        else:
            for status, amount in counts.items():
                if recorded_counts.get(status, amount) != amount:
                    errors.append({"error": "status count mismatch", "status": status, "expected": amount, "actual": recorded_counts.get(status)})
    recorded_coverage = certificate.get("byte_coverage")
    computed_coverage = covered / source_size if source_size else 1.0
    if recorded_coverage is not None and recorded_coverage != computed_coverage:
        errors.append({"error": "byte coverage mismatch", "expected": computed_coverage, "actual": recorded_coverage})
    return {
        "ok": not errors,
        "source_size": source_size,
        "covered_bytes": covered,
        "byte_coverage": computed_coverage,
        "instruction_coverage": certificate.get("instruction_coverage"),
        "analysis_mode": certificate.get("analysis_mode"),
        "unpack_mode": certificate.get("unpack_mode"),
        "text_source": certificate.get("text_source"),
        "status_bytes": counts,
        "errors": errors,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("certificate", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        result = validate_intervals(load_json(args.certificate), args.source)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"ok": False, "errors": [{"error": str(exc)}]}
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.report:
        args.report.write_text(encoded, encoding="utf-8")
    sys.stdout.write(encoded)
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
