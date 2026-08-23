from __future__ import annotations

import datetime as _dt
import os
import re
import sys

_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)([smhdw])$")


def parse_duration(text: str) -> float:
    m = _DURATION_RE.match(text.strip())
    if not m:
        raise ValueError(f"invalid duration {text!r}: use forms like 30s, 10m, 24h, 7d, 2w")
    return float(m.group(1)) * _UNITS[m.group(2)]


def parse_when(text: str | None, now: float) -> float | None:
    """Duration counted back from ``now``; ISO date/datetime parsed as-is."""
    if text is None:
        return None
    text = text.strip()
    try:
        return now - parse_duration(text)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return _dt.datetime.strptime(text, fmt).timestamp()
        except ValueError:
            continue
    raise ValueError(f"invalid --since/--until {text!r}: not a duration (24h) or ISO date (2026-08-01)")


def fmt_ts(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


class Style:
    """ANSI styling that only engages when the stream is a TTY."""

    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"
    DIM = "\033[2m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    def __init__(self, enabled: bool | None = None):
        if enabled is None:
            enabled = sys.stdout.isatty() and os.environ.get("TERM") != "dumb"
        self.enabled = enabled

    def _wrap(self, code: str, text: object) -> str:
        return f"{code}{text}{self.RESET}" if self.enabled else str(text)

    def good(self, text): return self._wrap(self.GREEN, text)
    def bad(self, text): return self._wrap(self.RED, text)
    def warn(self, text): return self._wrap(self.YELLOW, text)
    def accent(self, text): return self._wrap(self.CYAN, text)
    def dim(self, text): return self._wrap(self.DIM, text)
    def bold(self, text): return self._wrap(self.BOLD, text)
