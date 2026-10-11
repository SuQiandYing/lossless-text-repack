"""Check the unified skill entrypoints and engine catalog.

The original lossless skill checks remain authoritative and are intentionally
not reimplemented here. This script verifies that the copied base is present,
the engine catalog is coherent, links resolve, and shared Python files
parse without importing game or upstream code.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
BASE_REQUIRED = (
    "SKILL.md",
    "README.md",
    "references/PRESERVATION.md",
    "references/details/principles.md",
    "references/details/ir-layout.md",
    "references/details/repack.md",
    "references/details/verification.md",
    "scripts/run_gates.py",
    "tests/test_edit_gates.py",
)
SHARED_FILES = (
    "references/compatibility-architecture.md",
    "references/json-projection.md",
    "catalog/engines.json",
    "profiles/schema.json",
    "profiles/template.json",
    "python/core/model.py",
    "python/projections/json_projection.py",
    "python/detectors/candidates.py",
)
OPTIONAL_RUNTIME_IMPORTS = {
    "python/archives/nexas.py": {"zstandard"},
    "python/engines/yuris_ydg.py": {"PIL"},
    "python/engines/yuris_font.py": {"PIL", "fontTools"},
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def check() -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    stats = {"base_files": 0, "shared_files": 0, "engine_entries": 0, "python_files": 0}
    for relative in BASE_REQUIRED:
        if (ROOT / relative).is_file():
            stats["base_files"] += 1
        else:
            errors.append(f"missing copied base file: {relative}")

    copy_manifest = ROOT / "provenance/base-copy.json"
    if copy_manifest.is_file():
        try:
            snapshot = json.loads(_read(copy_manifest))
            files = snapshot.get("files", [])
            if snapshot.get("copied_file_count") != len(files):
                errors.append("base copy manifest count is inconsistent")
            for item in files:
                relative = item.get("path") if isinstance(item, dict) else None
                expected = item.get("sha256") if isinstance(item, dict) else None
                if not relative or not expected:
                    errors.append("base copy manifest contains a malformed file record")
                    continue
                target = ROOT / relative
                if not target.is_file():
                    errors.append(f"base copy file missing: {relative}")
                    continue
                if relative in {"SKILL.md", "README.md"}:
                    continue
                actual = hashlib.sha256(target.read_bytes()).hexdigest()
                if actual.lower() != expected.lower():
                    errors.append(f"preserved baseline file changed outside declared entrypoints: {relative}")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"base copy manifest parse failed: {exc}")
    else:
        errors.append("missing provenance/base-copy.json")
    for relative in SHARED_FILES:
        if (ROOT / relative).is_file():
            stats["shared_files"] += 1
        else:
            errors.append(f"missing extension file: {relative}")

    catalog_path = ROOT / "catalog/engines.json"
    if catalog_path.is_file():
        try:
            catalog = json.loads(_read(catalog_path))
            engines = catalog.get("engines")
            stats["engine_entries"] = len(engines) if isinstance(engines, list) else 0
            if catalog.get("count") != 95 or not isinstance(engines, list) or len(engines) != 95:
                errors.append("engine catalog must contain exactly 95 entries")
            ids: set[str] = set()
            for item in engines or []:
                if not isinstance(item, dict) or not item.get("id"):
                    errors.append("engine catalog contains a malformed entry")
                    continue
                if item["id"] in ids:
                    errors.append(f"duplicate engine id: {item['id']}")
                ids.add(item["id"])
                capabilities = item.get("capabilities", {})
                if capabilities.get("extract") != "catalog-only":
                    errors.append(f"unproven catalog entry upgraded without adapter: {item['id']}")
                if capabilities.get("repack") != "not_verified" or capabilities.get("runtime") != "not_verified":
                    errors.append(f"unproven catalog entry has an unsafe stage: {item['id']}")
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"catalog parse failed: {exc}")

    for path in sorted((ROOT / "python").rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        stats["python_files"] += 1
        relative = path.relative_to(ROOT).as_posix()
        try:
            tree = ast.parse(_read(path), filename=relative)
        except SyntaxError as exc:
            errors.append(f"{relative}: syntax error: {exc}")
            continue
        imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
        for node in imports:
            if isinstance(node, ast.ImportFrom) and node.level:
                continue
            names = [alias.name.split(".")[0] for alias in node.names] if isinstance(node, ast.Import) else [node.module.split(".")[0]] if node.module else []
            for name in names:
                allowed = OPTIONAL_RUNTIME_IMPORTS.get(relative, set())
                if (name not in {"python", "__future__"}
                        and name not in sys.stdlib_module_names
                        and name not in allowed):
                    errors.append(f"{relative}: non-stdlib import: {name}")

    for relative in ("references/compatibility-architecture.md", "references/json-projection.md"):
        path = ROOT / relative
        if not path.is_file():
            continue
        for target in re.findall(r"\]\(([^)#]+)(?:#[^)]+)?\)", _read(path)):
            if target.startswith(("http://", "https://")):
                continue
            if not (path.parent / target).resolve().is_file():
                errors.append(f"{relative}: broken local link: {target}")
    return errors, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Check the unified skill and engine catalog.")
    parser.parse_args()
    errors, stats = check()
    result = {"ok": not errors, "stats": stats, "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
