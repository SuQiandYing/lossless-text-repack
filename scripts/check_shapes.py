#!/usr/bin/env python3
"""Validate reported shape coverage, not parser semantics or traversal honesty.

Input: {declared:[signature], observed:{signature:{entries:N,texts:N}},
unmatched:{signature:N}}. Legacy integer observations lack text statistics and
yield not_verified. Corpus-wide claims require a separately supplied manifest
and exact scan identities. Exit: pass=0, fail=1, not_verified=2.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def load_json(path: Path) -> dict[str, Any]:
    def invalid(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")
    obj = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object, parse_constant=invalid)
    if not isinstance(obj, dict):
        raise ValueError("shape report root must be an object")
    return obj


def natural(value: Any, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(s, str) or not s.strip() for s in value):
        raise ValueError(f"{label} must be an array of nonempty strings")
    if len(value) != len(set(value)):
        raise ValueError(f"duplicate {label}")
    return value


def normalize_observed(raw: Any) -> dict[str, dict[str, int | None]]:
    if not isinstance(raw, dict):
        raise ValueError("observed must be an object")
    out = {}
    for sig, value in raw.items():
        if not isinstance(sig, str) or not sig.strip():
            raise ValueError("shape signature must be a nonempty string")
        if isinstance(value, dict):
            entries = natural(value.get("entries"), f"{sig}.entries")
            texts = natural(value["texts"], f"{sig}.texts") if "texts" in value else None
        else:
            entries, texts = natural(value, sig), None
        if entries == 0 and texts not in (None, 0):
            raise ValueError(f"{sig}: texts > 0 with no entries")
        out[sig] = {"entries": entries, "texts": texts}
    return out


def reason(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("reason"), str) or not value["reason"].strip():
        raise ValueError(f"{label} requires reason and evidence_refs")
    if not string_list(value.get("evidence_refs"), f"{label}.evidence_refs"):
        raise ValueError(f"{label} requires nonempty evidence_refs")
    return value


def manifest_rows(raw: Any, label: str) -> dict[str, str]:
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"{label} must be a nonempty array")
    out = {}
    for row in raw:
        if not isinstance(row, dict) or not isinstance(row.get("sample"), str) or not row["sample"].strip():
            raise ValueError(f"{label}: each entry requires sample")
        digest = row.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise ValueError(f"{label}: sha256 must contain 64 hex digits")
        if row["sample"] in out:
            raise ValueError(f"{label}: duplicate sample {row['sample']}")
        out[row["sample"]] = digest.lower()
    return out


def check(report: dict[str, Any], baseline: dict[str, Any] | None,
          corpus_wide: bool = False, corpus_manifest: Path | None = None) -> dict[str, Any]:
    if not isinstance(report, dict):
        raise ValueError("shape report must be an object")
    declared = set(string_list(report.get("declared"), "declared"))
    observed = normalize_observed(report.get("observed", {}))
    unmatched = report.get("unmatched", {})
    if not isinstance(unmatched, dict):
        raise ValueError("unmatched must be an object")
    for sig, count in unmatched.items():
        if not sig.strip():
            raise ValueError("unmatched signature must not be empty")
        natural(count, f"unmatched.{sig}")
    if set(unmatched) & set(observed):
        raise ValueError("observed and unmatched signatures overlap")
    inherited = report.get("inherited", {})
    nontext = report.get("nontext_shapes", {})
    for label, values in (("inherited", inherited), ("nontext_shapes", nontext)):
        if not isinstance(values, dict):
            raise ValueError(f"{label} must be an object")
        if set(values) - declared:
            raise ValueError(f"{label} contains undeclared signatures")
        for sig, value in values.items():
            # Historical inherited strings remain readable, but are unverified.
            if label == "inherited" and isinstance(value, str) and value.strip():
                continue
            reason(value, f"{label}.{sig}")
    issues, advisories, pending = [], [], []
    if not declared:
        issues.append({"code": "NO_DECLARED_SHAPES"})
    if sum(stat["entries"] for stat in observed.values()) + sum(unmatched.values()) == 0:
        pending.append({"code": "NO_OBSERVATION", "detail": "No positive entry statistics; enumeration not verified."})
    for sig, count in sorted(unmatched.items()):
        if count > 0:
            issues.append({"code": "UNDECLARED_SHAPE", "shape": sig, "entries": count})
    for sig in sorted(set(observed) - declared):
        issues.append({"code": "UNDECLARED_SHAPE", "shape": sig})
    for sig, stat in sorted(observed.items()):
        if stat["texts"] is None:
            pending.append({"code": "MISSING_TEXT_STATISTICS", "shape": sig})
        elif stat["entries"] > 0 and stat["texts"] == 0:
            if sig in nontext:
                advisories.append({"code": "NON_TEXT_SHAPE", "shape": sig, **nontext[sig]})
            else:
                issues.append({"code": "BARREN_SHAPE", "shape": sig})
    for sig in sorted(declared - {s for s, stat in observed.items() if stat["entries"] > 0}):
        entry = {"code": "UNUSED_SHAPE", "shape": sig}
        if sig in inherited:
            if isinstance(inherited[sig], str):
                pending.append({**entry, "detail": "Legacy inherited reason lacks evidence_refs."})
            else:
                advisories.append({**entry, **inherited[sig]})
        elif corpus_wide:
            issues.append(entry)
        else:
            advisories.append({**entry, "detail": "Not observed in this sample; no corpus-wide claim."})
    corpus_verified = False
    if corpus_wide:
        corpus = report.get("corpus")
        if corpus_manifest is None or not isinstance(corpus, dict):
            pending.append({"code": "MISSING_CORPUS_EVIDENCE", "detail": "Supply --corpus-manifest and report corpus scan identities."})
        else:
            payload = corpus_manifest.read_bytes()
            expected = manifest_rows(json.loads(payload.decode("utf-8-sig"), object_pairs_hook=unique_object), "manifest")
            actual = manifest_rows(corpus.get("scanned"), "corpus.scanned")
            if corpus.get("manifest_sha256") != hashlib.sha256(payload).hexdigest():
                issues.append({"code": "CORPUS_MANIFEST_HASH_MISMATCH"})
            if expected != actual:
                issues.append({"code": "CORPUS_COVERAGE_MISMATCH", "missing": sorted(set(expected) - set(actual)),
                               "extra": sorted(set(actual) - set(expected)),
                               "changed": sorted(k for k in set(actual) & set(expected) if actual[k] != expected[k])})
            corpus_verified = expected == actual and corpus.get("manifest_sha256") == hashlib.sha256(payload).hexdigest()
    elif corpus_manifest is not None:
        raise ValueError("--corpus-manifest requires --corpus-wide")
    if baseline is not None:
        base = normalize_observed(baseline.get("observed", {}))
        if not base or any(v["texts"] is None for v in base.values()):
            pending.append({"code": "BASELINE_INCOMPLETE"})
        if set(base) != set(observed):
            advisories.append({"code": "DISTRIBUTION_DRIFT", "added": sorted(set(observed) - set(base)),
                               "removed": sorted(set(base) - set(observed)),
                               "detail": "Different corpora may legitimately have different shapes; unknown handlers fail independently."})
    status = "fail" if issues else "not_verified" if pending else "pass"
    return {"ok": status == "pass", "status": status, "scope": "reported_shape_coverage",
            "declared_shapes": sorted(declared), "observed_shapes": observed,
            "total_entries": sum(s["entries"] for s in observed.values()),
            "total_texts": sum(s["texts"] or 0 for s in observed.values()),
            "unmatched_signatures": unmatched, "corpus_wide": corpus_wide,
            "corpus_scope_verified": corpus_verified, "issues": issues + pending,
            "issue_count": len(issues) + len(pending), "advisories": advisories,
            "note": "Checks report consistency and manifest membership, not traversal honesty or extraction semantics."}


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("shapes", type=Path)
    ap.add_argument("--baseline", type=Path)
    ap.add_argument("--corpus-wide", action="store_true")
    ap.add_argument("--corpus-manifest", type=Path)
    ap.add_argument("--report-out", type=Path)
    args = ap.parse_args(list(argv) if argv is not None else None)
    out = args.report_out
    try:
        inputs = [path for path in (args.shapes, args.baseline, args.corpus_manifest) if path is not None]
        if out and any(out.resolve() == path.resolve() or (out.exists() and path.exists() and out.samefile(path)) for path in inputs):
            out = None
            raise ValueError("report output must not overwrite report, baseline or manifest")
        result = check(load_json(args.shapes), load_json(args.baseline) if args.baseline else None,
                       args.corpus_wide, args.corpus_manifest)
    except (OSError, ValueError) as exc:
        result = {"ok": False, "status": "fail", "issues": [{"code": "INVALID_REPORT", "detail": str(exc)}]}
    result = _emit(result, out)
    return {"pass": 0, "fail": 1, "not_verified": 2}[result["status"]]


def _emit(result: dict[str, Any], out: Path | None) -> dict[str, Any]:
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if out:
        try:
            out.write_text(text, encoding="utf-8")
        except OSError as exc:
            result = {"ok": False, "status": "fail", "issues": [{"code": "REPORT_OUTPUT_ERROR", "detail": str(exc)}]}
            text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    sys.stdout.write(text)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
