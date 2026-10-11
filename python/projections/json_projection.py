"""Strict JSON projection with a manifest sidecar.

The JSON list is intentionally small and human-editable. Identity and source
proof live in the manifest, so an edited list can never silently select a
different script row.
"""

from __future__ import annotations

from typing import Any

from python.core.model import Change, ChangeSet, Document, ModelError


class ProjectionError(ValueError):
    """Raised when a JSON list or sidecar is unsafe to import."""


SCHEMA = "lossless-text-repack.json-manifest/1"


def _controls(entry: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in entry.controls]


def export_bundle(document: Document) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Return `(rows, manifest)` for all non-empty writable messages."""

    document.validate()
    rows: list[dict[str, str]] = []
    manifest_rows: list[dict[str, Any]] = []
    for entry in document.entries:
        if entry.message_policy != "writable" or entry.message == "":
            continue
        row: dict[str, str] = {"message": entry.message}
        if entry.name is not None and entry.name_policy in {"writable", "context"}:
            row["name"] = entry.name
        rows.append(row)
        manifest_rows.append(
            {
                "row_id": len(rows) - 1,
                "entry_id": entry.id,
                "source_text": entry.source_text,
                "name": entry.name,
                "name_policy": entry.name_policy,
                "controls": _controls(entry),
                "locator": entry.locator.to_dict() if entry.locator else None,
            }
        )
    return rows, {
        "schema": SCHEMA,
        "projection": "json",
        "source_sha256": document.source_sha256,
        "source_path": document.source_path,
        "engine": {"id": document.engine_id, "dialect": document.dialect},
        "rows": manifest_rows,
    }


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ProjectionError(f"{field} must be a string")
    return value


def import_bundle(
    document: Document,
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> ChangeSet:
    """Validate edited rows and create a ChangeSet; never writes game bytes."""

    document.validate()
    if not isinstance(rows, list) or not isinstance(manifest, dict):
        raise ProjectionError("rows must be a list and manifest an object")
    if manifest.get("schema") != SCHEMA:
        raise ProjectionError("unsupported JSON manifest schema")
    if manifest.get("projection") != "json":
        raise ProjectionError("manifest projection must be json")
    if manifest.get("source_sha256") != document.source_sha256:
        raise ProjectionError("manifest source hash does not match document")
    if manifest.get("source_path") != document.source_path:
        raise ProjectionError("manifest source path does not match document")
    engine = manifest.get("engine")
    if engine != {"id": document.engine_id, "dialect": document.dialect}:
        raise ProjectionError("manifest engine/dialect does not match document")
    manifest_rows = manifest.get("rows")
    if not isinstance(manifest_rows, list) or len(manifest_rows) != len(rows):
        raise ProjectionError("row count does not match manifest")
    _, fresh_manifest = export_bundle(document)
    fresh_rows = fresh_manifest["rows"]
    if [item.get("entry_id") for item in manifest_rows] != [item.get("entry_id") for item in fresh_rows]:
        raise ProjectionError("manifest row order does not match the current document")

    by_id = {entry.id: entry for entry in document.entries}
    changes: list[Change] = []
    seen_entry_ids: set[str] = set()
    for index, (row, meta) in enumerate(zip(rows, manifest_rows)):
        if not isinstance(row, dict) or not isinstance(meta, dict):
            raise ProjectionError(f"row {index} must be an object")
        if meta.get("row_id") != index:
            raise ProjectionError(f"row {index} has an invalid row_id")
        entry_id = meta.get("entry_id")
        entry = by_id.get(entry_id)
        if entry is None:
            raise ProjectionError(f"row {index} references unknown entry")
        if entry_id in seen_entry_ids:
            raise ProjectionError(f"row {index} duplicates entry identity")
        seen_entry_ids.add(entry_id)
        if meta.get("source_text") != entry.source_text:
            raise ProjectionError(f"row {index} source anchor is stale")
        if meta.get("name") != entry.name:
            raise ProjectionError(f"row {index} name anchor is stale")
        if meta.get("name_policy") != entry.name_policy:
            raise ProjectionError(f"row {index} name policy was changed")
        if meta.get("controls", []) != _controls(entry):
            raise ProjectionError(f"row {index} control metadata was changed")
        expected_locator = entry.locator.to_dict() if entry.locator else None
        if meta.get("locator") != expected_locator:
            raise ProjectionError(f"row {index} locator metadata was changed")
        message = _require_string(row.get("message"), f"row {index}.message")
        has_name = "name" in row
        name = _require_string(row["name"], f"row {index}.name") if has_name else None
        if entry.name_policy == "writable" and entry.name is not None and not has_name:
            raise ProjectionError(f"row {index} dropped its writable name")
        if entry.name_policy == "context" and name != entry.name:
            raise ProjectionError(f"row {index} changes a context-only name")
        if entry.name_policy == "readonly" and has_name:
            raise ProjectionError(f"row {index} added a read-only name")
        if entry.name_policy == "absent" and has_name:
            raise ProjectionError(f"row {index} added a name to an absent slot")
        if message == entry.message and name == entry.name:
            continue
        changes.append(
            Change(
                entry_id=entry.id,
                expected_source=entry.source_text,
                message=message if message != entry.message else None,
                name=name if name != entry.name else None,
            )
        )
    try:
        result = ChangeSet(
            source_sha256=document.source_sha256,
            document_id=f"{document.engine_id}:{document.dialect}:{document.source_sha256}",
            changes=tuple(changes),
        )
        result.validate()
        return result
    except ModelError as exc:
        raise ProjectionError(str(exc)) from exc
