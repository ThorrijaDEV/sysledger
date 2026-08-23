from __future__ import annotations

import os

from sysledger.collectors import collect_all, collect_packages, collect_services, collect_sysctl


class TestCollectPackages:
    def test_parses_pacman_local_entries(self, tmp_path):
        for name in ("linux-6.9.1.arch1-1", "python-pytest-mock-3.14.0-1", "btop-1.4.0-2"):
            (tmp_path / name).mkdir()
        pkgs = collect_packages(str(tmp_path))
        assert pkgs == {
            "linux": "6.9.1.arch1-1",
            "python-pytest-mock": "3.14.0-1",
            "btop": "1.4.0-2",
        }

    def test_malformed_entries_skipped(self, tmp_path):
        (tmp_path / "weird").mkdir()          # no hyphens at all
        (tmp_path / "-broken--").mkdir()       # empty parts
        assert collect_packages(str(tmp_path)) == {}

    def test_missing_root_is_empty(self, tmp_path):
        assert collect_packages(str(tmp_path / "nope")) == {}


class TestCollectSysctl:
    def test_walks_and_reads(self, tmp_path):
        (tmp_path / "vm").mkdir()
        (tmp_path / "net" / "core").mkdir(parents=True)
        (tmp_path / "vm" / "swappiness").write_text("60\n")
        (tmp_path / "net" / "core" / "somaxconn").write_text("4096")
        out = collect_sysctl(str(tmp_path))
        assert out == {"vm.swappiness": "60", "net.core.somaxconn": "4096"}

    def test_volatile_keys_excluded(self, tmp_path):
        (tmp_path / "fs").mkdir()
        (tmp_path / "kernel" / "random").mkdir(parents=True)
        (tmp_path / "vm").mkdir()
        (tmp_path / "fs" / "file-nr").write_text("1\t0\t9")
        (tmp_path / "kernel" / "random" / "uuid").write_text("abc")
        (tmp_path / "vm" / "stat").mkdir()
        (tmp_path / "vm" / "stat" / "pgfault").write_text("99")
        (tmp_path / "vm" / "swappiness").write_text("60")
        out = collect_sysctl(str(tmp_path))
        assert out == {"vm.swappiness": "60"}

    def test_unreadable_file_skipped(self, tmp_path):
        (tmp_path / "secret").write_text("x")
        os.chmod(tmp_path / "secret", 0)
        out = collect_sysctl(str(tmp_path))
        try:
            assert "secret" not in out or out["secret"] == "x"  # root ignores perms
        finally:
            os.chmod(tmp_path / "secret", 0o644)


def test_collect_services_parses_lines(monkeypatch):
    import sysledger.collectors as col

    class P:
        stdout = (
            "sshd.service enabled enabled\n"
            "docker.service disabled disabled\n"
            "user@1000.service static -\n"
            "notaservice thing\n"
        )

    monkeypatch.setattr(col.shutil, "which", lambda _: "/usr/bin/systemctl")
    monkeypatch.setattr(col.subprocess, "run", lambda *a, **k: P())
    assert collect_services() == {
        "sshd.service": "enabled",
        "docker.service": "disabled",
        "user@1000.service": "static",
    }


def test_collect_all_never_raises(monkeypatch):
    import sysledger.collectors as col

    def boom():
        raise RuntimeError("nope")

    monkeypatch.setattr(col, "COLLECTORS", {"pkg": boom, "kernel": lambda: {"k": "v"}})
    facts, errors = collect_all()
    assert facts["kernel"] == {"k": "v"}
    assert facts["pkg"] == {}
    assert "pkg" in errors


def test_collect_all_selected_subset(monkeypatch):
    import sysledger.collectors as col

    calls = []
    monkeypatch.setattr(col, "COLLECTORS", {
        "pkg": lambda: calls.append("pkg") or {},
        "svc": lambda: calls.append("svc") or {},
    })
    collect_all(selected=["pkg"])
    assert calls == ["pkg"]
