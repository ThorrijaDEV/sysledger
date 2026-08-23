from __future__ import annotations

import pytest

from sysledger.store import Store


@pytest.fixture()
def store(tmp_path):
    s = Store(tmp_path / "history.db")
    yield s
    s.close()


def snap_facts():
    return {"pkg": {"linux": "6.9"}}


class TestRecordAndGet:
    def test_roundtrip(self, store):
        sid = store.record(100.0, "box", "before update", snap_facts())
        got = store.get(sid)
        assert got[:4] == (sid, 100.0, "box", "before update")
        assert got[4] == {"pkg": {"linux": "6.9"}}

    def test_missing_snapshot(self, store):
        assert store.get(999) is None
        assert store.latest() is None

    def test_multiple_categories(self, store):
        facts = {
            "pkg": {"linux": "6.9"},
            "svc": {"sshd.service": "enabled"},
            "sysctl": {"vm.swappiness": "60"},
        }
        sid = store.record(1.0, "h", None, facts)
        assert store.get(sid)[4] == facts


class TestOrdering:
    def test_latest_by_ts(self, store):
        a = store.record(100.0, "h", "first", {})
        b = store.record(50.0, "h", "older-ts", {})   # inserted later, older ts
        c = store.record(200.0, "h", "newest", {})
        latest = store.latest()
        assert latest[0] in (a, b, c)
        # latest = highest id when no before_ts given? Spec: most recent record.
        assert latest[0] == c

    def test_latest_before_ts(self, store):
        store.record(100.0, "h", None, {})
        target = store.record(300.0, "h", None, {})
        found = store.latest(before_ts=250.0)
        assert found[0] != target

    def test_previous(self, store):
        first = store.record(10.0, "h", None, {})
        second = store.record(20.0, "h", None, {})
        third = store.record(30.0, "h", None, {})
        assert store.previous(third)[0] == second
        assert store.previous(first) is None
        assert store.previous(999) is None

    def test_list_snapshots_counts(self, store):
        store.record(1.0, "h", "n1", {"pkg": {"a": "1", "b": "2"}, "svc": {}})
        snaps = store.list_snapshots()
        assert snaps[0]["counts"] == {"pkg": 2}


def test_store_creates_parent_dirs(tmp_path):
    deep = tmp_path / "x" / "y" / "history.db"
    Store(deep).close()
    assert deep.exists()
