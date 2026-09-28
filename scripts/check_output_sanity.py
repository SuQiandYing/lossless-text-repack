#!/usr/bin/env python3
"""Check extraction-report plausibility, not completeness.

Accept a sample, nonempty array, JSONL, or {rows|samples|files: [...]}.
Counts are nonnegative integers. Required tags are domain-specific opt-ins;
skew/density warnings are advisory. Exit: pass=0, fail=1, not_verified=2.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterable

REQUIRED_TAGS: set[str] = set()
SKEW_THRESHOLD = 0.95
MAGNITUDE_RATIO = 0.10
DENSITY_SPREAD = 10.0
CONTAINER_EXPECT = {"dialog_entries": "msg", "select_entries": "choice"}
TAG_FIELDS = ("tags", "tag_counts", "export_tag_counts", "by_tag")


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_json(text: str) -> Any:
    def invalid(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")
    return json.loads(text, object_pairs_hook=unique_object, parse_constant=invalid)


def names(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        raise ValueError(f"{label} must be an array of nonempty strings")
    if len(set(value)) != len(value):
        raise ValueError(f"{label} contains duplicates")
    return value


def counts(value: Any, label: str) -> dict[str, int]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    for key, amount in value.items():
        if not isinstance(key, str) or not key.strip() or type(amount) is not int or amount < 0:
            raise ValueError(f"{label}.{key} must be a nonnegative integer")
    return value


def audited_reason(value: Any, label: str) -> None:
    if not isinstance(value, dict) or not isinstance(value.get("reason"), str) or not value["reason"].strip():
        raise ValueError(f"{label} requires a nonempty reason")
    if not names(value.get("evidence_refs"), f"{label}.evidence_refs"):
        raise ValueError(f"{label} requires evidence_refs")


def sample_name(row: dict[str, Any], index: int) -> str:
    for key in ("sample", "file", "name", "path"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value  # Full identity: equal basenames need not be equal samples.
    raise ValueError(f"sample[{index}] requires sample/file/name/path identity")


def tag_counts(row: dict[str, Any]) -> dict[str, int]:
    fields = [key for key in TAG_FIELDS if key in row]
    if len(fields) > 1:
        raise ValueError("ambiguous tag-count aliases")
    return counts(row[fields[0]], fields[0]) if fields else {}


def load_report(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise ValueError("report is empty")
    try:
        obj = parse_json(text)
    except json.JSONDecodeError:
        # JSONL starts with '{' too. Do not rescue duplicate keys or NaN here.
        obj = [parse_json(line) for line in text.splitlines() if line.strip()]
    metadata: dict[str, Any] = {}
    if isinstance(obj, dict):
        wrappers = [key for key in ("rows", "samples", "files") if key in obj]
        if len(wrappers) > 1:
            raise ValueError("ambiguous report wrapper")
        if wrappers:
            metadata = {key: obj[key] for key in ("domain", "required_tags") if key in obj}
            obj = obj[wrappers[0]]
        else:
            obj = [obj]
    if not isinstance(obj, list) or not obj:
        raise ValueError("report requires a nonempty sample array")
    rows = []
    identities = set()
    for index, value in enumerate(obj):
        if not isinstance(value, dict):
            raise ValueError(f"sample[{index}] must be an object")
        row = {**metadata, **value}
        identity = sample_name(row, index)
        if identity in identities:
            raise ValueError(f"duplicate sample identity: {identity}")
        identities.add(identity)
        tag_counts(row)
        for key in ("byte_size", "size"):
            if key in row and (type(row[key]) is not int or row[key] < 0):
                raise ValueError(f"{identity}.{key} must be a nonnegative integer")
        if "containers" in row:
            counts(row["containers"], "containers")
        if "domain" in row and (not isinstance(row["domain"], str) or not row["domain"].strip()):
            raise ValueError(f"{identity}.domain must be a nonempty string")
        required = names(row.get("required_tags", []), "required_tags")
        if required and not row.get("domain"):
            raise ValueError("required_tags requires an explicitly declared domain")
        if "waivers" in row:
            if not isinstance(row["waivers"], dict):
                raise ValueError("waivers must be an object")
            for tag, waiver in row["waivers"].items():
                if not tag.strip():
                    raise ValueError("waiver tag must not be empty")
                audited_reason(waiver, f"waivers.{tag}")
        if "allow_empty" in row:
            audited_reason(row["allow_empty"], "allow_empty")
        rows.append(row)
    return rows


def check_sample(row: dict[str, Any], index: int,
                 required: set[str] | None = None) -> list[dict[str, Any]]:
    name = sample_name(row, index)
    tags = tag_counts(row)
    required = set(required or ()) | set(row.get("required_tags", []))
    issues: list[dict[str, Any]] = []
    if not any(key in row for key in TAG_FIELDS):
        return [{"sample": name, "code": "NO_TAG_COUNTS", "severity": "not_verified",
                 "detail": "No tag counts supplied; output plausibility was not checked."}]
    total = sum(tags.values())
    if total == 0 and not row.get("allow_empty"):
        issues.append({"sample": name, "code": "EMPTY_OUTPUT", "severity": "fail",
                       "detail": "No text extracted; allow_empty needs evidence that the sample contains no text."})
    for tag in sorted(required):
        if tags.get(tag, 0) == 0:
            issues.append({"sample": name, "code": "REQUIRED_TAG_ZERO", "severity": "fail",
                           "detail": f"Declared domain requires tag={tag}, but count is zero."})
    # Omitted and explicit zero fields must produce the same verdict.
    positive = {key: amount for key, amount in tags.items() if amount > 0}
    if total and len(positive) > 1:
        tag, amount = max(positive.items(), key=lambda pair: pair[1])
        if amount / total > SKEW_THRESHOLD:
            issues.append({"sample": name, "code": "SKEWED_OUTPUT", "severity": "advisory",
                           "detail": f"{tag}: {amount}/{total}; review against this sample's declared domain."})
    for key, tag in CONTAINER_EXPECT.items():
        declared = row.get("containers", {}).get(key, 0)
        if declared > 0 and tags.get(tag, 0) < declared * MAGNITUDE_RATIO:
            issues.append({"sample": name, "code": "MAGNITUDE_MISMATCH", "severity": "fail",
                           "detail": f"{key}={declared}, but {tag}={tags.get(tag, 0)}."})
    return issues


def check_density(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points = [(sample_name(row, i), sum(tag_counts(row).values()) / row.get("byte_size", row.get("size", 0)))
              for i, row in enumerate(rows) if row.get("byte_size", row.get("size", 0)) > 0]
    if len(points) < 2:
        return []
    lo_name, lo = min(points, key=lambda pair: pair[1])
    hi_name, hi = max(points, key=lambda pair: pair[1])
    if (lo == 0 and hi > 0) or (lo > 0 and hi / lo > DENSITY_SPREAD):
        return [{"code": "DENSITY_SPREAD", "severity": "advisory",
                 "detail": f"Density differs: {lo_name}={lo}, {hi_name}={hi}. Domain/content may differ."}]
    return []


def main(argv: Iterable[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("report", type=Path)
    ap.add_argument("--require-tag", action="append", default=[])
    ap.add_argument("--domain", help="Domain to which CLI required tags apply")
    ap.add_argument("--allow-zero", action="append", default=[], help="Requires per-sample audited waivers")
    ap.add_argument("--report-out", type=Path)
    args = ap.parse_args(list(argv) if argv is not None else None)
    out = args.report_out
    try:
        if out and (out.resolve() == args.report.resolve() or (out.exists() and args.report.exists() and out.samefile(args.report))):
            out = None
            raise ValueError("report output must not overwrite the input report")
        rows = load_report(args.report)
        required = set(names(args.require_tag, "--require-tag"))
        allowed = set(names(args.allow_zero, "--allow-zero"))
        if args.domain is not None and not args.domain.strip():
            raise ValueError("--domain must not be empty")
        if required and not args.domain and not all(row.get("domain") for row in rows):
            raise ValueError("--require-tag requires --domain or a report domain")
        issues = []
        applied_waivers = []
        for index, row in enumerate(rows):
            effective = required | set(row.get("required_tags", []))
            for tag in allowed & effective:
                audited_reason(row.get("waivers", {}).get(tag), f"{sample_name(row, index)}.waivers.{tag}")
                applied_waivers.append({"sample": sample_name(row, index), "tag": tag, **row["waivers"][tag]})
            row = {**row, "required_tags": []}
            issues.extend(check_sample(row, index, effective - allowed))
        issues.extend(check_density(rows))
        failures = [issue for issue in issues if issue["severity"] == "fail"]
        pending = [issue for issue in issues if issue["severity"] == "not_verified"]
        status = "fail" if failures else "not_verified" if pending else "pass"
        result = {"ok": status == "pass", "status": status, "samples": len(rows),
                  "scope": "report_plausibility_only", "required_tags": sorted(required),
                  "issues": failures + pending, "issue_count": len(failures) + len(pending),
                  "advisories": [i for i in issues if i["severity"] == "advisory"],
                  "waivers_applied": applied_waivers,
                  "checks_skipped": [{"sample": sample_name(row, i), "check": "magnitude", "status": "not_applicable",
                                      "reason": "Optional container-count comparison was not declared."}
                                     for i, row in enumerate(rows) if not row.get("containers")],
                  "note": "Pass checks recorded counts only, not whether all text was found or correctly classified."}
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
    write_stdout(text)
    return result


def write_stdout(text: str) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
    sys.stdout.write(text)


if __name__ == "__main__":
    raise SystemExit(main())
