"""Small bounded detector used by the shared adapter workflow.

The detector reports hypotheses only. It never imports an engine adapter or
turns a file-name match into permission to extract or repack.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable


DEFAULT_HEAD_LIMIT = 64 * 1024


@dataclass(frozen=True)
class Candidate:
    path: str
    profile: str
    score: float
    signals: tuple[str, ...]
    counter_evidence: tuple[str, ...] = ()
    status: str = "candidate"

    def to_dict(self) -> dict[str, object]:
        result = asdict(self)
        result["signals"] = list(self.signals)
        result["counter_evidence"] = list(self.counter_evidence)
        return result


class AmbiguousCandidate(ValueError):
    """Raised when no explicit profile resolves competing candidates."""


def _head(path: Path, limit: int) -> bytes:
    if limit <= 0:
        raise ValueError("head limit must be positive")
    with path.open("rb") as stream:
        return stream.read(limit)


def detect_path(
    path: str | Path,
    *,
    head_limit: int = DEFAULT_HEAD_LIMIT,
    max_files: int = 4096,
) -> list[Candidate]:
    """Return bounded structural hints for one file or a directory tree."""

    root = Path(path)
    if max_files <= 0:
        raise ValueError("max_files must be positive")
    paths = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())[:max_files] if root.is_dir() else []
    candidates: list[Candidate] = []
    for item in paths:
        if not item.is_file():
            continue
        head = _head(item, head_limit)
        hints: list[tuple[str, str, float]] = []
        if head.startswith(b"XP3"):
            hints.append(("kirikiri-xp3", "magic:XP3", 0.92))
        if head.startswith((b"PFS", b"PFS\x00")):
            hints.append(("artemis-pfs", "magic:PFS", 0.88))
        if head.startswith((b"ARC1", b"ARC2")):
            hints.append(("arc-index", "magic:ARC", 0.72))
        if head.startswith(b"PK\x03\x04"):
            hints.append(("zip-container", "magic:ZIP", 0.45))
        if head.startswith(b"MZ"):
            hints.append(("native-executable", "magic:MZ", 0.30))
        for profile, signal, score in hints:
            candidates.append(
                Candidate(
                    path=str(item),
                    profile=profile,
                    score=score,
                    signals=(signal, f"size:{item.stat().st_size}"),
                )
            )
    return sorted(candidates, key=lambda item: (-item.score, item.path, item.profile))


def resolve(candidates: Iterable[Candidate], *, profile: str | None = None, minimum: float = 0.5) -> Candidate:
    """Resolve only an explicit profile or a unique strong candidate."""

    items = list(candidates)
    if profile is not None:
        matches = [item for item in items if item.profile == profile]
        if len(matches) != 1:
            raise AmbiguousCandidate(f"explicit profile {profile!r} did not match exactly one candidate")
        return matches[0]
    strong = [item for item in items if item.score >= minimum]
    if not strong:
        raise AmbiguousCandidate("no candidate reached the evidence threshold")
    if len(strong) > 1 and strong[0].score == strong[1].score:
        raise AmbiguousCandidate("competing candidates have equal evidence")
    return strong[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit bounded engine candidates; never selects a writer.")
    parser.add_argument("path")
    parser.add_argument("--head-limit", type=int, default=DEFAULT_HEAD_LIMIT)
    parser.add_argument("--max-files", type=int, default=4096)
    args = parser.parse_args(argv)
    path = Path(args.path)
    if not path.exists():
        parser.error(f"path does not exist: {path}")
    payload = {
        "schema": "lossless-text-repack.candidates/1",
        "path": str(path),
        "source_head_sha256": sha256_head(path, args.head_limit),
        "candidates": [item.to_dict() for item in detect_path(path, head_limit=args.head_limit, max_files=args.max_files)],
        "status": "candidate-only",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def sha256_head(path: Path, limit: int) -> str:
    if path.is_file():
        return hashlib.sha256(_head(path, limit)).hexdigest()
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
