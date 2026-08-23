from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path
from typing import Optional

from sysledger import collectors, report as fmt
from sysledger.diff import counts_by_category, diff_facts
from sysledger.format import Style, fmt_ts, parse_when
from sysledger.model import CATEGORY_LABELS
from sysledger.store import Store

DEFAULT_DB = Path(
    os.environ.get("SYSLDGER_DB")
    or os.environ.get("SYSLEDGER_DB")
    or Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    / "sysledger"
    / "history.db"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sysledger",
        description="A ledger of your Linux machine: snapshot its configuration, diff it over time.",
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB,
                        help="SQLite history file (default: %(default)s)")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    sub = parser.add_subparsers(dest="command", required=True)

    p_snap = sub.add_parser("snapshot", help="record the current system facts")
    p_snap.add_argument("--note", help="short label stored with this snapshot")
    p_snap.add_argument("--only", metavar="CATS", help="comma-separated subset: pkg,svc,sysctl,kernel")

    p_log = sub.add_parser("log", help="list recorded snapshots")
    p_log.add_argument("--json", action="store_true", dest="as_json")

    p_diff = sub.add_parser("diff", help="compare two snapshots")
    p_diff.add_argument("--from", dest="src", type=int, metavar="ID")
    p_diff.add_argument("--to", dest="dst", type=int, metavar="ID")
    p_diff.add_argument("--since", metavar="DUR|ISO",
                        help="use the newest snapshot older than this point")
    p_diff.add_argument("--only", metavar="CATS", help="restrict to categories")
    p_diff.add_argument("--json", action="store_true", dest="as_json")

    p_show = sub.add_parser("show", help="print every fact of one snapshot")
    p_show.add_argument("id", nargs="?", default="latest")
    p_show.add_argument("--only", metavar="CATS")
    p_show.add_argument("--json", action="store_true", dest="as_json")

    return parser


def _selected(raw: Optional[str]) -> Optional[list[str]]:
    if not raw:
        return None
    cats = [c.strip() for c in raw.split(",") if c.strip()]
    unknown = [c for c in cats if c not in CATEGORY_LABELS]
    if unknown:
        raise ValueError(f"unknown categories: {', '.join(unknown)} (valid: {', '.join(CATEGORY_LABELS)})")
    return cats


def cmd_snapshot(args, store: Store, style: Style) -> int:
    selected = _selected(args.only)
    ts = time.time()
    facts, errors = collectors.collect_all(selected)
    sid = store.record(ts, socket.gethostname(), args.note, facts)
    total = sum(len(v) for v in facts.values())
    print(style.bold(f"Snapshot {sid} recorded at {fmt_ts(ts)} — {total} facts."))
    for cat in sorted(facts):
        label = CATEGORY_LABELS[cat]
        print(f"  {label:<10} {len(facts[cat]):>6}")
    for cat, err in errors.items():
        print(style.bad(f"  {CATEGORY_LABELS.get(cat, cat):<10} failed: {err}"), file=sys.stderr)
    return 0


def cmd_log(args, store: Store, style: Style) -> int:
    snaps = store.list_snapshots()
    if args.as_json:
        out = [{**s, "timestamp": s.pop("ts")} for s in snaps]
        print(json.dumps(out, indent=2))
        return 0
    print(fmt.render_log(snaps, style))
    return 0


def _resolve_pair(args, store: Store, style: Style):
    dst = store.latest() if getattr(args, "dst", None) is None else store.get(args.dst)
    if dst is None:
        raise ValueError("no such snapshot" if args.dst else
                         "nothing recorded yet — run: sysledger snapshot")
    if args.src is not None:
        src = store.get(args.src)
        if src is None:
            raise ValueError(f"no such snapshot: {args.src}")
    elif getattr(args, "since", None):
        now = time.time()
        cutoff = parse_when(args.since, now)
        assert cutoff is not None
        candidate = store.latest(before_ts=cutoff)
        if candidate is None:
            candidate = _oldest(store)
            if candidate is None:
                raise ValueError("only one snapshot exists; nothing to compare")
            print(style.dim(f"No snapshot older than {args.since}; using the oldest one "
                            f"(#{candidate[0]})."), file=sys.stderr)
        src = candidate
    else:
        src = store.previous(dst[0])
        if src is None:
            raise ValueError("only one snapshot exists so far; take another one first")
    return src, dst


def _oldest(store: Store):
    snaps = store.list_snapshots()
    if len(snaps) < 2:
        return None
    return store.get(snaps[0]["id"])


def cmd_diff(args, store: Store, style: Style) -> int:
    selected = _selected(getattr(args, "only", None))
    src, dst = _resolve_pair(args, store, style)
    changes = [
        c for c in diff_facts(src[4], dst[4])
        if selected is None or c.category in selected
    ]
    if args.as_json:
        print(fmt.to_json_changes(changes))
        return 0
    header = style.bold(f"Snapshot #{src[0]} ({fmt_ts(src[1])}) → #{dst[0]} ({fmt_ts(dst[1])})")
    body = fmt.render_diff(changes, style)
    print(f"{header}\n{body}")
    if changes:
        print(style.dim(f"\nTotal: {fmt.render_summary(changes)}"))
    return 0


def cmd_show(args, store: Store, style: Style) -> int:
    snap = store.latest() if str(args.id) == "latest" else store.get(int(args.id))
    if snap is None:
        raise ValueError(f"no such snapshot: {args.id}" if str(args.id) != "latest"
                         else "nothing recorded yet — run: sysledger snapshot")
    sid, ts, host, note, facts = snap
    selected = _selected(args.only)
    if selected is not None:
        facts = {k: v for k, v in facts.items() if k in selected}
    if args.as_json:
        print(fmt.snapshot_facts_json(sid, ts, host, facts))
        return 0
    print(style.bold(f"Snapshot #{sid} — {fmt_ts(ts)} — {host}" + (f' — "{note}"' if note else "")))
    for cat in sorted(facts):
        print(style.bold(CATEGORY_LABELS.get(cat, cat)))
        for key, value in sorted(facts[cat].items()):
            print(f"  {key} = {value}")
    return 0


COMMANDS = {
    "snapshot": cmd_snapshot,
    "log": cmd_log,
    "diff": cmd_diff,
    "show": cmd_show,
}


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    style = Style(enabled=False if args.no_color else None)
    store = Store(args.db)
    try:
        return COMMANDS[args.command](args, store, style)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
