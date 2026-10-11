"""Bounded candidate detectors; they never choose an engine writer."""

from .candidates import AmbiguousCandidate, Candidate, detect_path, resolve

__all__ = ["AmbiguousCandidate", "Candidate", "detect_path", "resolve"]
