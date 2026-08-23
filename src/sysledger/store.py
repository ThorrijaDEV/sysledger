from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots(
  id INTEGER PRIMARY KEY,
  ts REAL NOT NULL,
  host TEXT NOT NULL,
  note TEXT
);
CREATE TABLE IF NOT EXISTS facts(
  snapshot_id INTEGER NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
  category TEXT NOT NULL,
  key TEXT NOT NULL,
  value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_facts_snapshot ON facts(snapshot_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_ts ON snapshots(ts);
"""


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def record(self, ts: float, host: str, note: Optional[str], facts: dict[str, dict[str, str]]) -> int:
        cur = self.conn.execute("INSERT INTO snapshots (ts, host, note) VALUES (?, ?, ?)", (ts, host, note))
        sid = int(cur.lastrowid)
        self.conn.executemany(
            "INSERT INTO facts (snapshot_id, category, key, value) VALUES (?, ?, ?, ?)",
            [
                (sid, cat, key, value)
                for cat, entries in facts.items()
                for key, value in sorted(entries.items())
            ],
        )
        self.conn.commit()
        return sid

    def _load_facts(self, sid: int) -> dict[str, dict[str, str]]:
        facts: dict[str, dict[str, str]] = {}
        for cat, key, value in self.conn.execute(
            "SELECT category, key, value FROM facts WHERE snapshot_id = ? ORDER BY category, key", (sid,)
        ):
            facts.setdefault(cat, {})[key] = value
        return facts

    def _ref(self, row) -> dict:
        return {"id": row[0], "ts": row[1], "host": row[2], "note": row[3], "facts": None}

    def get(self, sid: int) -> Optional[tuple]:
        """(id, ts, host, note, facts) or None."""
        row = self.conn.execute("SELECT id, ts, host, note FROM snapshots WHERE id = ?", (sid,)).fetchone()
        if row is None:
            return None
        return (row[0], row[1], row[2], row[3], self._load_facts(sid))

    def latest(self, before_ts: Optional[float] = None) -> Optional[tuple]:
        """Most recent snapshot, optionally strictly older than a timestamp."""
        if before_ts is None:
            row = self.conn.execute(
                "SELECT id, ts, host, note FROM snapshots ORDER BY id DESC LIMIT 1"
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT id, ts, host, note FROM snapshots WHERE ts <= ? ORDER BY ts DESC, id DESC LIMIT 1",
                (before_ts,),
            ).fetchone()
        if row is None:
            return None
        return (row[0], row[1], row[2], row[3], self._load_facts(row[0]))

    def previous(self, sid: int) -> Optional[tuple]:
        """Snapshot immediately preceding the given one."""
        anchor = self.conn.execute("SELECT ts FROM snapshots WHERE id = ?", (sid,)).fetchone()
        if anchor is None:
            return None
        row = self.conn.execute(
            "SELECT id, ts, host, note FROM snapshots WHERE ts < ? OR (ts = ? AND id < ?)"
            " ORDER BY ts DESC, id DESC LIMIT 1",
            (anchor[0], anchor[0], sid),
        ).fetchone()
        if row is None:
            return None
        return (row[0], row[1], row[2], row[3], self._load_facts(row[0]))

    def list_snapshots(self) -> list[dict]:
        rows = self.conn.execute("SELECT id, ts, host, note FROM snapshots ORDER BY id").fetchall()
        counts: dict[int, dict[str, int]] = {}
        for sid, cat, n in self.conn.execute(
            "SELECT snapshot_id, category, COUNT(*) FROM facts GROUP BY snapshot_id, category"
        ):
            counts.setdefault(sid, {})[cat] = n
        return [
            {"id": r[0], "ts": r[1], "host": r[2], "note": r[3], "counts": counts.get(r[0], {})}
            for r in rows
        ]

    def close(self):
        self.conn.close()
