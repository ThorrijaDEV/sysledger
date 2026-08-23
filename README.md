# sysledger

A ledger of your Linux machine: **snapshot its configuration, diff it over time.**

Your system changes constantly — updates land, services get toggled, kernel parameters get tweaked. A week later something breaks and the only question that matters is *"what changed?"*. Package managers know what they did; nothing tells you what **everything else** did.

sysledger takes point-in-time snapshots of your machine's configuration into a local SQLite database and diffs any two of them:

```
$ sysledger diff --since 24h
Snapshot #41 (2026-08-22 09:00:02) → #42 (2026-08-23 09:00:01)
Packages
  ~ linux: 6.9.1.arch1-1 → 6.10.1.arch1-1
  + linux-headers = 6.10.1.arch1-1
Services
  ~ docker.service: enabled → disabled
Sysctl
  ~ vm.swappiness: 60 → 20

Total: 2 packages changed, 1 service changed, 1 sysctl changed.
```

## Why

- After an Arch update breaks something, see exactly which versions moved.
- Prove that "nothing changed on the server" (or find out what did).
- Track down who disabled that service months ago — keep snapshots in a cron job and query history like a log.

## Features

- **Four fact families**: installed packages (`pacman` local DB), systemd unit states, kernel parameters (`/proc/sys`), kernel/OS identity.
- **Diff anything**: previous vs latest, explicit snapshot IDs, or `--since 24h`.
- **Zero dependencies**: pure Python standard library. SQLite storage, no daemons.
- **Failure-tolerant collectors**: one broken category never aborts the snapshot.
- **Scriptable**: `--json` on every command, honest ANSI colors only on TTYs.
- **Small and boring on purpose**: single binary, local data, `~/.local/state/sysledger/`.

## Installation

Requires Python ≥ 3.9 on Linux (pacman-related facts are Arch-specific; everything else works anywhere with systemd or `/proc/sys`).

```bash
git clone https://github.com/ThorrijaDEV/sysledger
cd sysledger
python3 -m venv .venv && source .venv/bin/activate
pip install .
sysledger --help
```

Or with [uv](https://docs.astral.sh/uv/) / pipx:

```bash
uv tool install git+https://github.com/ThorrijaDEV/sysledger
```

## Usage

### Record and compare

```bash
sysledger snapshot --note "before big update"
# ... do things ...
sysledger snapshot --note "after big update"
sysledger diff                      # last two snapshots
sysledger diff --from 3 --to 7      # explicit IDs
sysledger diff --since 24h          # newest vs ~this time yesterday
```

### Browse

```bash
sysledger log                       # all snapshots with timestamps and notes
sysledger show latest               # every recorded fact
sysledger show 12 --only pkg        # just the packages of snapshot #12
sysledger show latest --json | jq .facts.pkg.linux
```

### Automate it

Daily snapshots via a user systemd timer (`~/.config/systemd/user/sysledger.timer`):

```ini
[Timer]
OnCalendar=daily
Persistent=true
```

Pair it with a hook-style workflow — snapshot before and after `yay -Syu`, then `sysledger diff` tells you the story of the update.

## The fact families

| Category | Source | Notes |
|---|---|---|
| `pkg` | `/var/lib/pacman/local/` | name → version; read directly, no subprocess |
| `svc` | `systemctl list-unit-files` | unit → state (`enabled`, `static`, ...) |
| `sysctl` | walk of `/proc/sys` | dotted keys (`vm.swappiness`); unreadable entries skipped |
| `kernel` | `uname`, `/etc/os-release` | release, architecture, distro name |

Select a subset anytime with `--only pkg,svc`.

## Configuration

| Setting | Default |
|---|---|
| Database path | `$XDG_STATE_HOME/sysledger/history.db` |
| Override | `SYSLEDGER_DB=/path/to.db` env var or global `--db PATH` |

No config files. Schema is created automatically; delete the file to start fresh.

## How it works

```
collectors (pkg/svc/sysctl/kernel)      SQLite ledger           queries
┌───────────────────────────────┐  ──▶  snapshots(id, ts,   ──▶  log / show
│ {category: {key: value}}      │       host, note)            diff (pure fn)
└───────────────────────────────┘       facts(snapshot_id…)     json output
```

A *fact* is `(category, key, value)` — e.g. `("pkg", "linux", "6.10.1")`. Snapshots are full fact sets; diffs are computed in memory by set comparison, so schema stays trivial and new categories are one function away.

## Limitations

- Packages come from pacman's local DB: Arch and derivatives only for the `pkg` family (other families still work).
- Unit *file* state, not runtime state — use `systemctl status` for whether something is actually running.
- No secrets are collected, but sysctl values can describe security posture; treat the database as semi-sensitive.
- Polling model: changes between two snapshots are invisible until the next snapshot.

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e . pytest
pytest
```

Tests are fully offline: fake pacman trees, fake systemctl output, tmp-path databases.

```
src/sysledger/
├── model.py       # Change / SnapshotRef / categories
├── collectors.py  # fact sources, each independently testable
├── diff.py        # pure set-comparison logic
├── store.py       # SQLite ledger
├── format.py      # durations, timestamps, ANSI style
├── report.py      # human & JSON rendering
└── cli.py         # argparse wiring
tests/
```

## Roadmap

- [ ] Flatpak/other package managers as extra `pkg-*` categories
- [ ] `watch` mode: continuous polling with event log (like port-authority)
- [ ] Exit code contract: `diff --fail-on-change` for CI/cron alerting
- [ ] HTML report export

## License

[MIT](LICENSE)
