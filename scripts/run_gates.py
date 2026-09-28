#!/usr/bin/env python3
"""Run an explicit, scoped gate plan. Never interprets shell commands."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

GATES = frozenset({
    "check_dsat", "check_sites", "check_output_sanity", "check_shapes",
    "coverage_certificate", "check_determinism", "check_no_literals",
})
CODES = {"pass": 0, "fail": 1, "not_verified": 2}


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ValueError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_plan(path):
    plan = json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object)
    if not isinstance(plan, dict) or plan.get("schema_version") != 1 or isinstance(plan.get("schema_version"), bool):
        raise ValueError("plan requires schema_version=1")
    if set(plan) - {"schema_version", "scope", "checks", "not_applicable", "timeout_seconds"}:
        raise ValueError("unknown plan fields")
    if not isinstance(plan.get("scope"), str) or not plan["scope"].strip():
        raise ValueError("plan requires a nonempty scope")
    checks = plan.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("checks must be a nonempty list")
    excluded = plan.get("not_applicable", {})
    if not isinstance(excluded, dict) or any(k not in GATES or not isinstance(v, str) or not v.strip() for k, v in excluded.items()):
        raise ValueError("not_applicable requires known gate names and nonempty reasons")
    ids, active = set(), set()
    for c in checks:
        if not isinstance(c, dict) or set(c) != {"id", "gate", "args"}:
            raise ValueError("each check requires exactly id, gate, args")
        if not isinstance(c["id"], str) or not c["id"].strip() or c["id"] in ids:
            raise ValueError("check id must be nonempty and unique")
        if not isinstance(c["gate"], str) or c["gate"] not in GATES:
            raise ValueError("gate is not in the executable whitelist")
        if not isinstance(c["args"], list) or any(not isinstance(a, str) or "\0" in a for a in c["args"]):
            raise ValueError("args must be an array of strings without NUL")
        ids.add(c["id"])
        active.add(c["gate"])
    if active & set(excluded):
        raise ValueError("an active gate cannot also be not_applicable")
    if active | set(excluded) != GATES:
        raise ValueError("each gate needs an active check or explicit not_applicable reason")
    timeout = plan.get("timeout_seconds", 120)
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise ValueError("timeout_seconds must be an integer in [1,3600]")
    return plan


def run(plan, base):
    results = []
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
    for check in plan["checks"]:
        command = [sys.executable, "-B", str(Path(__file__).with_name(check["gate"] + ".py")), *check["args"]]
        row = {"id": check["id"], "gate": check["gate"], "command": command, "cwd": str(base)}
        try:
            p = subprocess.run(command, cwd=base, env=environment, capture_output=True,
                               text=True, encoding="utf-8", errors="strict",
                               timeout=plan.get("timeout_seconds", 120), shell=False)
            row.update(exit_code=p.returncode, stdout=p.stdout, stderr=p.stderr)
            report = json.loads(p.stdout, object_pairs_hook=unique_object)
            if not isinstance(report, dict) or report.get("status") not in CODES:
                raise ValueError("child did not produce a gate status")
            status = report["status"]
            if p.returncode != CODES[status] or report.get("ok") is not (status == "pass"):
                raise ValueError("child status, ok and exit code disagree")
            row.update(status=status, report=report)
        except subprocess.TimeoutExpired as e:
            def text_value(value):
                return value.decode("utf-8", errors="backslashreplace") if isinstance(value, bytes) else (value or "")
            row.update(status="not_verified", exit_code=None, stdout=text_value(e.stdout),
                       stderr=text_value(e.stderr), error="GATE_TIMEOUT")
        except (OSError, UnicodeError) as e:
            row.update(status="not_verified", error="GATE_EXECUTION_ERROR", detail=str(e))
        except (ValueError, TypeError) as e:
            row.update(status="fail", error="GATE_PROTOCOL_ERROR", detail=str(e))
        results.append(row)
    statuses = {r["status"] for r in results}
    status = "fail" if "fail" in statuses else "not_verified" if "not_verified" in statuses else "pass"
    return {"status": status, "ok": status == "pass", "scope": plan["scope"],
            "guarantee": "listed checks only; applicability and semantic correctness need independent review",
            "not_applicable": plan.get("not_applicable", {}), "checks": results}


def main(argv=None):
    parser = Parser(description=__doc__)
    parser.add_argument("plan", type=Path)
    try:
        args = parser.parse_args(argv)
        path = args.plan.resolve()
        report = run(load_plan(path), path.parent)
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as e:
        report = {"status": "fail", "ok": False, "errors": [{"code": "INVALID_PLAN", "detail": str(e)}]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return CODES[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
