# tests/test_cc_signals.py
import json
import os
import time

import pytest

from desk_buddy import cc_signals


@pytest.fixture
def pending(tmp_path, monkeypatch):
    d = tmp_path / "pending"
    monkeypatch.setattr(cc_signals, "pending_dir", lambda: d)
    return d


def test_write_then_read_roundtrip(pending):
    cc_signals.write_pending("sess-1", "needs your permission to use Bash")
    assert cc_signals.read_pending() == {"sess-1"}
    data = json.loads((pending / "sess-1.json").read_text("utf-8"))
    assert data["session_id"] == "sess-1"
    assert "permission" in data["message"]


def test_clear_removes_only_that_session(pending):
    cc_signals.write_pending("a")
    cc_signals.write_pending("b")
    cc_signals.clear_pending("a")
    assert cc_signals.read_pending() == {"b"}


def test_clear_missing_is_silent(pending):
    cc_signals.clear_pending("nope")  # must not raise


def test_read_missing_dir_is_empty(pending):
    assert cc_signals.read_pending() == set()


def test_read_tolerates_corrupt_file(pending):
    pending.mkdir(parents=True, exist_ok=True)
    (pending / "broken.json").write_text("{ not json", encoding="utf-8")
    cc_signals.write_pending("good")
    assert cc_signals.read_pending() == {"good"}


def test_safe_name_filters_illegal_chars(pending):
    cc_signals.write_pending("a/b\\c:d")
    files = list(pending.glob("*.json"))
    assert len(files) == 1
    assert files[0].name == "a_b_c_d.json"


def test_prune_stale_drops_old_keeps_fresh(pending):
    cc_signals.write_pending("old")
    cc_signals.write_pending("fresh")
    old = pending / "old.json"
    past = time.time() - 7200
    os.utime(old, (past, past))
    cc_signals.prune_stale(max_age_seconds=600)
    assert cc_signals.read_pending() == {"fresh"}
