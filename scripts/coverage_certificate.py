#!/usr/bin/env python3
"""Validate a byte-coverage certificate against a local source file."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
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
TIERS = {f"T{i}" for i in range(5)}
CAPABILITIES = {"coverage": 0, "roundtrip": 0, "identity": 0, "text-export": 2,
                "in_place": 2, "pointer-rewrite": 2, "full-layout": 2,
                "control-flow-edit": 4, "instruction-edit": 4}


def load_json(path: Path) -> dict[str, Any]:
    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")
    with path.open("r", encoding="utf-8-sig") as handle:
        value = json.load(handle, object_pairs_hook=reject_duplicate, parse_constant=reject_constant)
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


def ratio(value: Any, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{label} must be a finite numeric ratio in [0, 1]")
    return float(value)


def string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError(f"{label} must be an array of nonempty strings")
    if len(set(value)) != len(value):
        raise ValueError(f"duplicate {label}")
    return value


def validate_tiers(certificate: dict[str, Any], intervals: list[dict[str, Any]],
                   source_size: int) -> dict[str, Any]:
    """Check declarations and arithmetic, never claim to prove their semantics."""
    capabilities = string_list(certificate.get("declared_capabilities", []), "declared_capabilities")
    for capability in capabilities:
        if capability not in CAPABILITIES:
            raise ValueError(f"unknown declared capability: {capability}")
    scopes = certificate.get("capability_scopes", {})
    if not isinstance(scopes, dict) or set(scopes) - set(capabilities):
        raise ValueError("capability_scopes must map declared capabilities to scope objects")
    for capability, scope in scopes.items():
        if not isinstance(scope, dict) or not string_list(scope.get("scope_region_ids"), "scope_region_ids"):
            raise ValueError(f"capability_scopes.{capability} requires nonempty scope_region_ids")
        if "operation_kind" in scope and scope["operation_kind"] not in ("data", "instruction"):
            raise ValueError(f"capability_scopes.{capability}.operation_kind must be data or instruction")
    tier_claimed = any(key in certificate for key in ("min_tier", "declared_tier", "tier_coverage")) or any(
        isinstance(item, dict) and "decode_tier" in item for item in intervals)
    if not tier_claimed:
        return {"tier_claims_checked": False, "tier_coverage": None, "min_tier": None,
                "capability_tier_consistency": "not_verified", "capability_semantics": "not_verified"}
    counts = {tier: 0 for tier in sorted(TIERS)}
    evidence = certificate.get("evidence", {})
    if not isinstance(evidence, dict):
        raise ValueError("evidence must be an object keyed by evidence id")
    for key, item in evidence.items():
        if not key.strip() or not isinstance(item, dict):
            raise ValueError("invalid evidence record")
        if item.get("kind") not in ("observed", "derived", "inferred", "unresolved"):
            raise ValueError(f"evidence.{key}.kind is invalid")
        if not isinstance(item.get("source"), str) or not item["source"].strip():
            raise ValueError(f"evidence.{key}.source is required")
    tiers = []
    for index, item in enumerate(intervals):
        if not isinstance(item, dict):
            raise ValueError(f"interval[{index}] must be an object")
        if not isinstance(item.get("id"), str) or not item["id"].strip():
            raise ValueError(f"interval[{index}] requires a string id")
        tier = item.get("decode_tier")
        if not isinstance(tier, str) or tier not in TIERS:
            raise ValueError(f"interval[{index}].decode_tier must be T0..T4")
        number = int(tier[1])
        length = integer(item.get("end"), "end") - integer(item.get("start"), "start")
        counts[tier] += length
        tiers.append(number)
        refs = string_list(item.get("tier_evidence_refs", []), "tier_evidence_refs")
        if any(ref not in evidence for ref in refs):
            raise ValueError(f"interval[{index}] references absent evidence")
        if number >= 1:
            if not refs or not any(evidence[ref]["kind"] in ("observed", "derived") for ref in refs):
                raise ValueError(f"interval[{index}] requires traceable observed/derived evidence")
            boundary_model = item.get("boundary_model", "cell-stream")
            if boundary_model == "cell-stream":
                cell_size = integer(item.get("cell_size"), "cell_size")
                cell_count = integer(item.get("cell_count"), "cell_count")
                if cell_size <= 0 or cell_count <= 0 or cell_size * cell_count != length:
                    raise ValueError(f"interval[{index}] invalid cell partition")
                if item.get("endianness") not in ("little", "big", "not_applicable"):
                    raise ValueError(f"interval[{index}] invalid endianness")
            elif boundary_model in ("structured", "instruction"):
                boundary_refs = string_list(item.get("boundary_evidence_refs"), "boundary_evidence_refs")
                if not boundary_refs or any(ref not in evidence for ref in boundary_refs):
                    raise ValueError("boundary model requires resolvable boundary_evidence_refs")
                if not any(evidence[ref]["kind"] in ("observed", "derived") for ref in boundary_refs):
                    raise ValueError("boundary model requires observed/derived boundary evidence")
                if boundary_model == "instruction" and number < 3:
                    raise ValueError("instruction boundaries require T3 or higher")
            else:
                raise ValueError("boundary_model must be cell-stream, structured or instruction")
        if number >= 2:
            structured = item.get("structured_fields", item.get("text_structure"))
            if structured is not None and (not isinstance(structured, (list, dict)) or not structured):
                raise ValueError("structured_fields/text_structure must be a nonempty array or object")
            if "anchor_ids" in item:
                anchors = string_list(item["anchor_ids"], "anchor_ids")
                for key in ("anchor_hit_count", "join_site_count"):
                    if integer(item.get(key), key) < 0:
                        raise ValueError(f"{key} must be nonnegative")
            else:
                anchors = []
            if not anchors and not structured:
                raise ValueError(f"interval[{index}] requires anchors or parsed structural text fields")
        if number >= 3:
            if not isinstance(item.get("length_algorithm"), str) or not item["length_algorithm"].strip():
                raise ValueError(f"interval[{index}] requires length_algorithm")
            if not isinstance(item.get("operand_schema"), (dict, list)):
                raise ValueError(f"interval[{index}] requires operand_schema")
        if number >= 4:
            for key in ("labels", "targets", "basic_blocks", "cfg_edges"):
                if not isinstance(item.get(key), list):
                    raise ValueError(f"interval[{index}] requires {key} array")
            if not item["basic_blocks"]:
                raise ValueError(f"interval[{index}] requires a nonempty CFG")
    minimum = f"T{min(tiers)}" if tiers else None
    if source_size <= 0 or sum(counts.values()) != source_size:
        raise ValueError("tier byte counts must sum to positive source_size")
    for key in ("min_tier", "declared_tier"):
        if key in certificate and certificate[key] != minimum:
            raise ValueError(f"{key} does not equal the minimum interval tier {minimum}")
    recorded = certificate.get("tier_coverage")
    if recorded is not None:
        if not isinstance(recorded, dict) or set(recorded) - TIERS:
            raise ValueError("tier_coverage must contain only T0..T4 byte counts")
        for tier in TIERS:
            if integer(recorded.get(tier, 0), f"tier_coverage.{tier}") != counts[tier]:
                raise ValueError(f"tier_coverage.{tier} mismatch")
    region_tiers = {item.get("id"): int(item["decode_tier"][1]) for item in intervals}
    capability_scope_checks = {}
    for capability, scope in scopes.items():
        if not isinstance(scope, dict):
            raise ValueError(f"capability_scopes.{capability} must contain scope_region_ids")
        ids = string_list(scope.get("scope_region_ids"), "scope_region_ids")
        if not ids or set(ids) - set(region_tiers):
            raise ValueError(f"invalid scope_region_ids for {capability}")
        required_tier = CAPABILITIES[capability]
        check = {"scope_region_ids": ids, "required_tier": f"T{required_tier}"}
        if capability == "full-layout":
            # Missing operation_kind authorizes only the data-layout threshold;
            # it never implies instruction or control-flow rewrite capability.
            operation_kind = scope.get("operation_kind", "data")
            required_tier = 3 if operation_kind == "instruction" else 2
            check.update({"operation_kind": operation_kind,
                          "operation_kind_defaulted": "operation_kind" not in scope,
                          "required_tier": f"T{required_tier}",
                          "scope": "instruction_layout_tier_only" if operation_kind == "instruction" else "data_layout_tier_only"})
        if min(region_tiers[region] for region in ids) < required_tier:
            raise ValueError(f"capability {capability} exceeds an affected region's tier")
        capability_scope_checks[capability] = check
    instruction = certificate.get("instruction_coverage")
    instruction_ratio = (counts["T3"] + counts["T4"]) / source_size
    if instruction is not None:
        if instruction == "not_applicable":
            if instruction_ratio > 0:
                raise ValueError("instruction_coverage cannot be not_applicable when T3/T4 regions exist")
        elif ratio(instruction, "instruction_coverage") != instruction_ratio:
            raise ValueError("instruction_coverage must equal T3/T4 bytes divided by source_size")
    return {"tier_claims_checked": True, "tier_coverage": counts, "min_tier": minimum,
            "computed_instruction_coverage": instruction_ratio,
            "capability_scope_checks": capability_scope_checks,
            "capability_tier_consistency": "checked" if set(scopes) == set(capabilities) else "not_verified",
            "capability_semantics": "not_verified"}


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
        if value is not None and (not isinstance(value, str) or value not in allowed):
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
                    ratio(instruction_coverage, "instruction_coverage")
                except ValueError:
                    errors.append({"error": "instruction_coverage must be a ratio in [0, 1] or not_applicable"})
    return errors


def validate_intervals(certificate: dict[str, Any], source: Path) -> dict[str, Any]:
    source_size = integer(certificate.get("source_size"), "source_size")
    if source_size < 0:
        raise ValueError("source_size must be nonnegative")
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
    tier_result = {"tier_claims_checked": False}
    try:
        tier_result = validate_tiers(certificate, raw_intervals, source_size)
    except ValueError as exc:
        errors.append({"error": str(exc)})
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
            if not isinstance(status, str) or status not in STATUSES:
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
            for status, amount in recorded_counts.items():
                if status not in STATUSES or type(amount) is not int or amount < 0:
                    errors.append({"error": "invalid status count", "status": status})
            for status, amount in counts.items():
                if recorded_counts.get(status, 0) != amount:
                    errors.append({"error": "status count mismatch", "status": status, "expected": amount, "actual": recorded_counts.get(status)})
    computed_coverage = covered / source_size if source_size else 1.0
    for key in ("byte_coverage", "structural_coverage"):
        if key in certificate:
            try:
                declared_ratio = ratio(certificate[key], key)
                if key == "byte_coverage" and declared_ratio != computed_coverage:
                    errors.append({"error": f"{key} mismatch", "expected": computed_coverage, "actual": certificate[key]})
            except ValueError as exc:
                errors.append({"error": str(exc)})
    if "source_sha256" in certificate:
        expected = certificate["source_sha256"]
        if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected) or expected.lower() != stream_sha256(source, 0, source_size):
            errors.append({"error": "source_sha256 mismatch or malformed"})
    if "instruction_coverage" in certificate and not tier_result.get("tier_claims_checked") and certificate["instruction_coverage"] != "not_applicable":
        errors.append({"error": "numeric instruction_coverage requires interval tier declarations"})
    status = "fail" if errors else "not_verified" if source_size == 0 else "pass"
    return {
        "ok": status == "pass", "status": status,
        "scope": "byte_partition_hashes_and_declared_tier_consistency",
        **tier_result,
        "source_size": source_size,
        "covered_bytes": covered,
        "byte_coverage": computed_coverage,
        "structural_coverage": certificate.get("structural_coverage"),
        "structural_coverage_verification": "not_verified",
        "instruction_coverage": certificate.get("instruction_coverage"),
        "analysis_mode": certificate.get("analysis_mode"),
        "unpack_mode": certificate.get("unpack_mode"),
        "text_source": certificate.get("text_source"),
        "status_bytes": counts,
        "errors": errors,
        "note": "Validates byte hashes and declaration consistency only. Structural coverage is a self-reported ratio, not inferred from byte coverage. Evidence independence, semantic understanding, transforms, and roundtrip require separate verification. Empty sources verify no useful coverage.",
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("certificate", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    out = args.report
    try:
        if out and any(out.resolve() == path.resolve() or (out.exists() and path.exists() and out.samefile(path))
                       for path in (args.source, args.certificate)):
            out = None
            raise ValueError("report output must not overwrite source or certificate")
        result = validate_intervals(load_json(args.certificate), args.source)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"ok": False, "status": "fail", "errors": [{"error": str(exc)}]}
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if out:
        try:
            out.write_text(encoded, encoding="utf-8")
        except OSError as exc:
            result = {"ok": False, "status": "fail", "errors": [{"error": f"report output: {exc}"}]}
            encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    sys.stdout.write(encoded)
    return {"pass": 0, "fail": 1, "not_verified": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
