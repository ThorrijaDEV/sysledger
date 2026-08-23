from __future__ import annotations

from sysledger.model import Change


def diff_facts(prev: dict[str, dict[str, str]], curr: dict[str, dict[str, str]]) -> list[Change]:
    """Pure comparison of two fact sets; deterministic order by (category, key, kind)."""
    changes: list[Change] = []
    for cat in sorted(set(prev) | set(curr)):
        p = prev.get(cat, {})
        c = curr.get(cat, {})
        for key in sorted(set(p) - set(c)):
            changes.append(Change(category=cat, kind="removed", key=key, old=p[key]))
        for key in sorted(set(c) - set(p)):
            changes.append(Change(category=cat, kind="added", key=key, new=c[key]))
        for key in sorted(set(p) & set(c)):
            if p[key] != c[key]:
                changes.append(Change(category=cat, kind="changed", key=key, old=p[key], new=c[key]))
    return changes


def counts_by_category(changes: list[Change]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for ch in changes:
        counts[ch.category] = counts.get(ch.category, 0) + 1
    return counts
