from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Change:
    category: str
    kind: str  # added | removed | changed
    key: str
    old: str | None = None
    new: str | None = None

    @property
    def symbol(self) -> str:
        return {"added": "+", "removed": "-", "changed": "~"}[self.kind]


CATEGORY_LABELS = {
    "pkg": "Packages",
    "svc": "Services",
    "sysctl": "Sysctl",
    "kernel": "Kernel",
}

CATEGORIES = tuple(CATEGORY_LABELS)


@dataclass(frozen=True)
class SnapshotRef:
    id: int
    ts: float
    host: str
    note: str | None = None
    counts: dict[str, int] | None = None
