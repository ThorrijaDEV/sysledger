from __future__ import annotations

import json
import time

import pytest

import sysledger.cli as cli


@pytest.fixture()
def db(tmp_path):
    return str(tmp_path / "history.db")


FAKE_SNAPSHOT = {
    "pkg": {"linux": "6.9.1.arch1-1", "btop": "1.4.0-2"},
    "svc": {"sshd.service": "enabled"},
}


def patch_collectors(monkeypatch, sequence):
    """Sequence of fact dicts returned by successive collect_all calls."""
    calls = iter(sequence)
    monkeypatch.setattr(
        cli.collectors, "collect_all",
        lambda selected=None: (dict(next(calls)), {}),
    )


class TestSnapshotAndLog:
    def test_snapshot_reports_counts(self, db, monkeypatch, capsys):
        patch_collectors(monkeypatch, [FAKE_SNAPSHOT])
        rc = cli.main(["--db", db, "snapshot", "--note", "base"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "Snapshot 1 recorded" in out
        assert "Packages" in out and "Services" in out

    def test_log_lists_snapshots(self, db, monkeypatch, capsys):
        patch_collectors(monkeypatch, [FAKE_SNAPSHOT, FAKE_SNAPSHOT])
        cli.main(["--db", db, "snapshot"])
        time.sleep(0.01)
        cli.main(["--db", db, "snapshot", "--note", "second"])
        rc = cli.main(["--db", db, "log"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "base" not in out and "second" in out

    def test_log_json(self, db, monkeypatch, capsys):
        patch_collectors(monkeypatch, [FAKE_SNAPSHOT])
        cli.main(["--db", db, "snapshot"])
        capsys.readouterr()
        rc = cli.main(["--db", db, "log", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert data[0]["counts"]["pkg"] == 2
        assert "timestamp" in data[0]


class TestDiff:
    def test_previous_vs_latest(self, db, monkeypatch, capsys):
        second = {**FAKE_SNAPSHOT,
                  "pkg": {**FAKE_SNAPSHOT["pkg"], "htop": "3.3.0-1"},
                  "svc": {},
                  "sysctl": {"vm.swappiness": "10"}}
        patch_collectors(monkeypatch, [FAKE_SNAPSHOT, second])
        cli.main(["--db", db, "snapshot"])
        time.sleep(0.01)
        cli.main(["--db", db, "snapshot"])
        rc = cli.main(["--db", db, "diff"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "+ htop = 3.3.0-1" in out
        assert "- sshd.service (was enabled)" in out
        assert "~ vm.swappiness:  → 10".replace("~ ", "~ ") in out or "vm.swappiness" in out

    def test_since_picks_older(self, db, monkeypatch, capsys):
        v1 = {"pkg": {"a": "1"}}
        v2 = {"pkg": {"a": "2"}}
        v3 = {"pkg": {"a": "3"}}
        patch_collectors(monkeypatch, [v1, v2, v3])
        cli.main(["--db", db, "snapshot"])
        time.sleep(0.02)
        cli.main(["--db", db, "snapshot"])
        time.sleep(0.02)
        cli.main(["--db", db, "snapshot"])
        rc = cli.main(["--db", db, "diff", "--since", "1h"])
        out = capsys.readouterr().out
        # All snapshots are younger than 1h → falls back to oldest (#1 vs #3).
        assert rc == 0
        assert "~ a: 1 → 3" in out

    def test_from_to_ids(self, db, monkeypatch, capsys):
        patch_collectors(monkeypatch, [{"pkg": {"a": "1"}}, {"pkg": {"a": "2"}}, {"pkg": {"a": "3"}}])
        cli.main(["--db", db, "snapshot"])
        time.sleep(0.01)
        cli.main(["--db", db, "snapshot"])
        time.sleep(0.01)
        cli.main(["--db", db, "snapshot"])
        rc = cli.main(["--db", db, "diff", "--from", "1", "--to", "2"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "~ a: 1 → 2" in out and "→ 3" not in out

    def test_only_filters_categories(self, db, monkeypatch, capsys):
        second = {"pkg": {"linux": "6.10"}, "svc": {}}
        patch_collectors(monkeypatch, [FAKE_SNAPSHOT, second])
        cli.main(["--db", db, "snapshot"])
        time.sleep(0.01)
        cli.main(["--db", db, "snapshot"])
        rc = cli.main(["--db", db, "diff", "--only", "svc"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "sshd.service" in out and "linux" not in out.split("\n")[1]

    def test_json_output(self, db, monkeypatch, capsys):
        patch_collectors(monkeypatch, [FAKE_SNAPSHOT, {"pkg": {}}])
        cli.main(["--db", db, "snapshot"])
        time.sleep(0.01)
        cli.main(["--db", db, "snapshot"])
        capsys.readouterr()
        rc = cli.main(["--db", db, "diff", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert rc == 0
        kinds = {(d["category"], d["kind"]) for d in data}
        assert ("pkg", "removed") in kinds
        assert ("svc", "removed") in kinds

    def test_single_snapshot_error(self, db, monkeypatch, capsys):
        patch_collectors(monkeypatch, [FAKE_SNAPSHOT])
        cli.main(["--db", db, "snapshot"])
        rc = cli.main(["--db", db, "diff"])
        err = capsys.readouterr()
        assert rc == 2
        assert "only one snapshot" in err.err

    def test_no_snapshots_error(self, db, capsys):
        rc = cli.main(["--db", db, "diff"])
        assert rc == 2
        assert "nothing recorded yet" in capsys.readouterr().err

    def test_bad_category_rejected(self, db, monkeypatch):
        rc = cli.main(["--db", db, "diff", "--only", "nope"])
        assert rc == 2


class TestShow:
    def test_show_latest(self, db, monkeypatch, capsys):
        patch_collectors(monkeypatch, [FAKE_SNAPSHOT])
        cli.main(["--db", db, "snapshot"])
        rc = cli.main(["--db", db, "show", "latest"])
        out = capsys.readouterr().out
        assert rc == 0
        assert "linux = 6.9.1.arch1-1" in out

    def test_show_json_subset(self, db, monkeypatch, capsys):
        patch_collectors(monkeypatch, [FAKE_SNAPSHOT])
        cli.main(["--db", db, "snapshot"])
        capsys.readouterr()
        rc = cli.main(["--db", db, "show", "--only", "svc", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert data["facts"] == {"svc": {"sshd.service": "enabled"}}


def test_parse_when_duration():
    from sysledger.format import parse_when

    now = 1_000_000.0
    assert parse_when("24h", now) == now - 86400
    assert parse_when(None, now) is None
