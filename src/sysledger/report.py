from __future__ import annotations

import json
from typing import Iterable, Optional

from sysledger.format import Style, fmt_ts
from sysledger.model import CATEGORY_LABELS, Change, SnapshotRef


def _change_dict(ch: Change) -> dict:
    return {
        "category": ch.category,
        "kind": ch.kind,
        "key": ch.key,
        "old": ch.old,
        "new": ch.new,
    }


def render_diff(changes: Iterable[Change], style: Style) -> str:
    by_cat: dict[str, list[Change]] = {}
    for ch in changes:
        by_cat.setdefault(ch.category, []).append(ch)
    if not by_cat:
        return style.good("No changes.")
    blocks = []
    for cat in sorted(by_cat):
        label = CATEGORY_LABELS.get(cat, cat)
        lines = [style.bold(label)]
        for ch in by_cat[cat]:
            if ch.kind == "added":
                detail = style.good(f"+ {ch.key} = {ch.new}")
            elif ch.kind == "removed":
                detail = style.bad(f"- {ch.key} (was {ch.old})")
            else:
                detail = style.warn(f"~ {ch.key}: {ch.old} → {ch.new}")
            lines.append("  " + detail)
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


def to_json_changes(changes: Iterable[Change]) -> str:
    return json.dumps([_change_dict(c) for c in changes], indent=2)


def render_log(snapshots: list[dict], style: Style) -> str:
    if not snapshots:
        return style.dim("No snapshots yet. Run: sysledger snapshot")
    header = f"{'ID':>4}  {'TIMESTAMP':<19}  {'HOST':<16}  {'FACTS':>7}  NOTE"
    sep = "-" * len(header)
    rows = [header, sep]
    for snap in snapshots:
        total = sum(snap["counts"].values())
        note = snap["note"] or ""
        rows.append(
            f"{snap['id']:>4}  {fmt_ts(snap['ts']):<19}  {snap['host']:<16.16}  {total:>7}  {note}"
        )
    return "\n".join(rows)


def render_summary(changes: list[Change]) -> str:
    if not changes:
        return "No changes."
    parts = []
    for cat in sorted({c.category for c in changes}):
        n = sum(1 for c in changes if c.category == cat)
        label = CATEGORY_LABELS.get(cat, cat).lower()
        parts.append(f"{n} {label}" + ("s" if n != 1 and not label.endswith("s") else ""))
    return ", ".join(parts)


def snapshot_facts_json(snapshot_id: int, ts: float, host: str, facts: dict) -> str:
    return json.dumps({"id": snapshot_id, "timestamp": ts, "host": host, "facts": facts}, indent=2)
