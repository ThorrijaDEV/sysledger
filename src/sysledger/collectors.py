from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Callable, Optional

PACMAN_LOCAL = "/var/lib/pacman/local"
PROC_SYS = "/proc/sys"

# Runtime counters and per-boot values, not configuration: they change
# constantly and would drown every real diff in noise.
VOLATILE_SYSCTL_PREFIXES = (
    "fs.dentry-state",
    "fs.file-nr",
    "fs.inode-nr",
    "fs.inode-state",
    "fs.quota.",
    "kernel.ns_last_pid",
    "kernel.random.uuid",
    "kernel.random.boot_id",
    "vm.stat.",
    "net.netfilter.nf_conntrack_count",
)


def _is_volatile(key: str) -> bool:
    return any(key == p or key.startswith(p) or key.startswith(p.rstrip(".")) for p in VOLATILE_SYSCTL_PREFIXES)


def collect_packages(root: str = PACMAN_LOCAL) -> dict[str, str]:
    """Installed packages from the pacman local database (no subprocess).

    Directory names look like ``<name>-<pkgver>-<pkgrel>``; neither the
    version nor the release may contain a hyphen, so splitting the last
    two hyphens off is exact.
    """
    try:
        entries = sorted(os.listdir(root))
    except OSError:
        return {}
    pkgs: dict[str, str] = {}
    for entry in entries:
        parts = entry.rsplit("-", 2)
        if len(parts) == 3 and all(parts):
            pkgs[parts[0]] = f"{parts[1]}-{parts[2]}"
    return pkgs


def collect_services() -> dict[str, str]:
    """Unit-file states (enabled/disabled/static/...) from systemctl."""
    if shutil.which("systemctl") is None:
        return {}
    try:
        proc = subprocess.run(
            ["systemctl", "list-unit-files", "--type=service", "--plain", "--no-legend"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    units: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[0].endswith(".service"):
            units[fields[0]] = fields[1]
    return units


def collect_sysctl(root: str = PROC_SYS) -> dict[str, str]:
    """Readable kernel parameters, keys as dotted paths (vm.swappiness)."""
    out: dict[str, str] = {}
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, root)
            if _is_volatile(rel.replace(os.sep, ".")):
                continue
            try:
                with open(path, "rb") as fh:
                    raw = fh.read(1024)
                value = raw.decode("utf-8", "replace").strip().splitlines()
                out[rel.replace(os.sep, ".")] = value[0] if value else ""
            except (OSError, UnicodeError):
                continue
    return out


def _first_line(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as fh:
            lines = fh.read(256).decode("utf-8", "replace").splitlines()
        return lines[0].strip() if lines else None
    except OSError:
        return None


def collect_kernel() -> dict[str, str]:
    info = {
        "uname.release": platform.release(),
        "uname.machine": platform.machine(),
    }
    pretty = _first_line("/etc/os-release")
    # PRETTY_NAME="Arch Linux"
    for line in (pretty or "").splitlines():
        if line.startswith("PRETTY_NAME="):
            info["os"] = line.split("=", 1)[1].strip().strip('"')
            break
    return info


COLLECTORS: dict[str, Callable[[], dict[str, str]]] = {
    "pkg": collect_packages,
    "svc": collect_services,
    "sysctl": collect_sysctl,
    "kernel": collect_kernel,
}


def collect_all(selected: Optional[list[str]] = None) -> tuple[dict[str, dict[str, str]], dict[str, str]]:
    """Run collectors; a failing category never aborts the snapshot."""
    facts: dict[str, dict[str, str]] = {}
    errors: dict[str, str] = {}
    for cat, fn in COLLECTORS.items():
        if selected and cat not in selected:
            continue
        try:
            facts[cat] = dict(fn())
        except Exception as exc:
            errors[cat] = f"{type(exc).__name__}: {exc}"
            facts.setdefault(cat, {})
    return facts, errors
