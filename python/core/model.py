"""Small, strict IR used by the shared adapter and projection contracts.

This module intentionally does not parse any game format. Engine adapters build
these objects after their own evidence and boundary checks have passed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import copy
import hashlib
import json
from typing import Any, Iterable


class ModelError(ValueError):
    """Raised when an IR or ChangeSet violates its exchange contract."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ModelError(f"{field_name} must be a string")
    return value


@dataclass(frozen=True)
class Locator:
    member: str
    offset: int
    length: int
    unit: str = "bytes"

    def validate(self) -> None:
        _text(self.member, "locator.member")
        if self.offset < 0 or self.length < 0:
            raise ModelError("locator offset and length must be non-negative")
        if self.unit not in {"bytes", "code_units", "records"}:
            raise ModelError(f"unsupported locator unit: {self.unit}")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "member": self.member,
            "offset": self.offset,
            "length": self.length,
            "unit": self.unit,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "Locator":
        if not isinstance(value, dict):
            raise ModelError("locator must be an object")
        try:
            result = cls(
                member=_text(value["member"], "locator.member"),
                offset=value["offset"],
                length=value["length"],
                unit=value.get("unit", "bytes"),
            )
        except KeyError as exc:
            raise ModelError(f"missing locator field: {exc.args[0]}") from exc
        if not isinstance(result.offset, int) or not isinstance(result.length, int):
            raise ModelError("locator offset and length must be integers")
        result.validate()
        return result


@dataclass
class Entry:
    id: str
    kind: str
    message: str
    source_text: str
    name: str | None = None
    name_policy: str = "absent"
    message_policy: str = "writable"
    locator: Locator | None = None
    controls: list[dict[str, Any]] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    raw_hex: str | None = None
    evidence: list[str] = field(default_factory=list)

    def validate(self) -> None:
        for key in ("id", "kind", "message", "source_text"):
            _text(getattr(self, key), f"entry.{key}")
        if not self.id:
            raise ModelError("entry.id must not be empty")
        if self.name is not None:
            _text(self.name, "entry.name")
        if self.name_policy not in {"writable", "context", "absent", "readonly"}:
            raise ModelError(f"unsupported name policy: {self.name_policy}")
        if self.message_policy not in {"writable", "readonly"}:
            raise ModelError(f"unsupported message policy: {self.message_policy}")
        if self.locator is not None:
            self.locator.validate()
        if not isinstance(self.controls, list) or not isinstance(self.references, list):
            raise ModelError("controls and references must be lists")
        if not isinstance(self.evidence, list):
            raise ModelError("entry.evidence must be a list")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "name_policy": self.name_policy,
            "message": self.message,
            "message_policy": self.message_policy,
            "source_text": self.source_text,
            "locator": self.locator.to_dict() if self.locator else None,
            "controls": copy.deepcopy(self.controls),
            "references": list(self.references),
            "raw_hex": self.raw_hex,
            "evidence": list(self.evidence),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "Entry":
        if not isinstance(value, dict):
            raise ModelError("entry must be an object")
        try:
            result = cls(
                id=value["id"],
                kind=value["kind"],
                message=value["message"],
                source_text=value["source_text"],
                name=value.get("name"),
                name_policy=value.get("name_policy", "absent"),
                message_policy=value.get("message_policy", "writable"),
                locator=Locator.from_dict(value["locator"]) if value.get("locator") else None,
                controls=value.get("controls", []),
                references=value.get("references", []),
                raw_hex=value.get("raw_hex"),
                evidence=value.get("evidence", []),
            )
        except KeyError as exc:
            raise ModelError(f"missing entry field: {exc.args[0]}") from exc
        result.validate()
        return result


@dataclass
class Document:
    source_path: str
    source_sha256: str
    engine_id: str
    dialect: str
    entries: list[Entry] = field(default_factory=list)
    opaque_spans: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    schema: str = "lossless-text-repack.ir/1"

    def validate(self) -> None:
        if self.schema != "lossless-text-repack.ir/1":
            raise ModelError(f"unsupported document schema: {self.schema}")
        for field_name in ("source_path", "source_sha256", "engine_id", "dialect"):
            _text(getattr(self, field_name), f"document.{field_name}")
        if len(self.source_sha256) != 64 or any(c not in "0123456789abcdef" for c in self.source_sha256.lower()):
            raise ModelError("document.source_sha256 must be a SHA-256 hex string")
        seen: set[str] = set()
        for entry in self.entries:
            entry.validate()
            if entry.id in seen:
                raise ModelError(f"duplicate entry id: {entry.id}")
            seen.add(entry.id)
        if not isinstance(self.opaque_spans, list) or not isinstance(self.metadata, dict):
            raise ModelError("opaque_spans must be a list and metadata an object")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema": self.schema,
            "source": {"path": self.source_path, "sha256": self.source_sha256},
            "engine": {"id": self.engine_id, "dialect": self.dialect},
            "entries": [entry.to_dict() for entry in self.entries],
            "opaque_spans": copy.deepcopy(self.opaque_spans),
            "metadata": copy.deepcopy(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: Any) -> "Document":
        if not isinstance(value, dict):
            raise ModelError("document must be an object")
        try:
            source = value["source"]
            engine = value["engine"]
            result = cls(
                schema=value.get("schema", "lossless-text-repack.ir/1"),
                source_path=source["path"],
                source_sha256=source["sha256"],
                engine_id=engine["id"],
                dialect=engine["dialect"],
                entries=[Entry.from_dict(item) for item in value.get("entries", [])],
                opaque_spans=value.get("opaque_spans", []),
                metadata=value.get("metadata", {}),
            )
        except KeyError as exc:
            raise ModelError(f"missing document field: {exc.args[0]}") from exc
        result.validate()
        return result


@dataclass(frozen=True)
class Change:
    entry_id: str
    expected_source: str
    message: str | None = None
    name: str | None = None

    def validate(self) -> None:
        _text(self.entry_id, "change.entry_id")
        _text(self.expected_source, "change.expected_source")
        if self.message is None and self.name is None:
            raise ModelError("change must contain message or name")
        if self.message is not None:
            _text(self.message, "change.message")
        if self.name is not None:
            _text(self.name, "change.name")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        result: dict[str, Any] = {
            "entry_id": self.entry_id,
            "expected_source": self.expected_source,
        }
        if self.message is not None:
            result["message"] = self.message
        if self.name is not None:
            result["name"] = self.name
        return result


@dataclass(frozen=True)
class ChangeSet:
    source_sha256: str
    document_id: str
    changes: tuple[Change, ...]
    schema: str = "lossless-text-repack.changes/1"

    def validate(self) -> None:
        if self.schema != "lossless-text-repack.changes/1":
            raise ModelError(f"unsupported changes schema: {self.schema}")
        if len(self.source_sha256) != 64:
            raise ModelError("changes source_sha256 must be SHA-256")
        if not self.document_id:
            raise ModelError("changes document_id must not be empty")
        seen: set[str] = set()
        for change in self.changes:
            change.validate()
            if change.entry_id in seen:
                raise ModelError(f"duplicate change id: {change.entry_id}")
            seen.add(change.entry_id)

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "schema": self.schema,
            "source_sha256": self.source_sha256,
            "document_id": self.document_id,
            "changes": [change.to_dict() for change in self.changes],
        }


def apply_changes(document: Document, changes: ChangeSet) -> Document:
    """Apply checked changes to a copy of *document* without mutating it."""

    document.validate()
    changes.validate()
    if changes.source_sha256 != document.source_sha256:
        raise ModelError("source hash mismatch")
    updated = copy.deepcopy(document)
    by_id = {entry.id: entry for entry in updated.entries}
    for change in changes.changes:
        entry = by_id.get(change.entry_id)
        if entry is None:
            raise ModelError(f"unknown entry id: {change.entry_id}")
        if entry.source_text != change.expected_source:
            raise ModelError(f"stale source text for {change.entry_id}")
        if change.message is not None:
            if entry.message_policy != "writable":
                raise ModelError(f"message is read-only: {change.entry_id}")
            entry.message = change.message
        if change.name is not None:
            if entry.name_policy != "writable":
                raise ModelError(f"name is not writable: {change.entry_id}")
            entry.name = change.name
    updated.validate()
    return updated


def dumps(document: Document) -> str:
    return json.dumps(document.to_dict(), ensure_ascii=False, indent=2) + "\n"

