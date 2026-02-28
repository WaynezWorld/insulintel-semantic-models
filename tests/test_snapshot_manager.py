"""
Tests for app.snapshot_manager — snapshot save, list, prune, and helpers.

All tests use tmp_path to avoid touching the real .snapshots/ directory.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "app") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "app"))

from snapshot_manager import (
    save_snapshot,
    list_snapshots,
    get_latest_snapshot,
    load_snapshot,
    format_timestamp,
    snapshot_summary,
    _prune_snapshots,
    SNAPSHOT_DIR,
    MAX_SNAPSHOTS_PER_TARGET,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def snap_dir(tmp_path: Path):
    """Redirect SNAPSHOT_DIR to a temp directory for each test."""
    d = tmp_path / ".snapshots"
    d.mkdir()
    with patch("snapshot_manager.SNAPSHOT_DIR", d):
        yield d


def _make_snap(snap_dir: Path, target: str, action: str = "deploy",
               ts_suffix: str = "00") -> Path:
    """Write a minimal snapshot file and return its path."""
    ts = f"2025-01-15T12:{ts_suffix}:00+00:00"
    label = f"20250115T12{ts_suffix}00Z"
    data = {
        "timestamp": ts,
        "target_type": "Semantic View",
        "target": target,
        "action": action,
        "previous_state": {"field": "old"},
        "new_state": {"field": "new"},
    }
    path = snap_dir / f"{label}_{target}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Tests: save_snapshot
# ---------------------------------------------------------------------------

class TestSaveSnapshot:
    def test_creates_file(self, snap_dir: Path):
        path = save_snapshot(
            "Semantic View", "SEM_TEST",
            {"sg": "old text"}, {"sg": "new text"},
        )
        assert path.exists()
        assert path.suffix == ".json"
        assert "SEM_TEST" in path.name

    def test_content_is_valid_json(self, snap_dir: Path):
        path = save_snapshot(
            "Agent", "INSULINTEL",
            {"orchestration": "old"}, {"orchestration": "new"},
            action="revert",
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["target_type"] == "Agent"
        assert data["target"] == "INSULINTEL"
        assert data["action"] == "revert"
        assert data["previous_state"]["orchestration"] == "old"
        assert data["new_state"]["orchestration"] == "new"

    def test_timestamp_is_iso(self, snap_dir: Path):
        path = save_snapshot(
            "Semantic View", "SEM_X", {}, {},
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        # Should parse without error
        datetime.fromisoformat(data["timestamp"])

    def test_creates_dir_if_missing(self, tmp_path: Path):
        d = tmp_path / "nested" / ".snapshots"
        with patch("snapshot_manager.SNAPSHOT_DIR", d):
            path = save_snapshot("Semantic View", "SEM_Y", {}, {})
            assert d.exists()
            assert path.exists()


# ---------------------------------------------------------------------------
# Tests: list_snapshots
# ---------------------------------------------------------------------------

class TestListSnapshots:
    def test_lists_all(self, snap_dir: Path):
        _make_snap(snap_dir, "SEM_A", ts_suffix="01")
        _make_snap(snap_dir, "SEM_A", ts_suffix="02")
        _make_snap(snap_dir, "SEM_B", ts_suffix="03")
        result = list_snapshots()
        assert len(result) == 3

    def test_filters_by_target(self, snap_dir: Path):
        _make_snap(snap_dir, "SEM_A", ts_suffix="01")
        _make_snap(snap_dir, "SEM_B", ts_suffix="02")
        result = list_snapshots(target="SEM_A")
        assert len(result) == 1
        assert result[0]["target"] == "SEM_A"

    def test_respects_limit(self, snap_dir: Path):
        for i in range(5):
            _make_snap(snap_dir, "SEM_A", ts_suffix=f"{i:02d}")
        result = list_snapshots(limit=3)
        assert len(result) == 3

    def test_most_recent_first(self, snap_dir: Path):
        _make_snap(snap_dir, "SEM_A", ts_suffix="01")
        _make_snap(snap_dir, "SEM_A", ts_suffix="99")
        result = list_snapshots()
        assert result[0]["_filename"] > result[1]["_filename"]

    def test_empty_dir(self, snap_dir: Path):
        result = list_snapshots()
        assert result == []

    def test_nonexistent_dir(self, tmp_path: Path):
        with patch("snapshot_manager.SNAPSHOT_DIR", tmp_path / "nope"):
            result = list_snapshots()
            assert result == []


# ---------------------------------------------------------------------------
# Tests: get_latest_snapshot
# ---------------------------------------------------------------------------

class TestGetLatestSnapshot:
    def test_returns_latest(self, snap_dir: Path):
        _make_snap(snap_dir, "SEM_A", ts_suffix="10")
        _make_snap(snap_dir, "SEM_A", ts_suffix="20")
        result = get_latest_snapshot("SEM_A")
        assert result is not None
        assert "20" in result["_filename"]

    def test_returns_none_if_missing(self, snap_dir: Path):
        result = get_latest_snapshot("SEM_NOTHING")
        assert result is None


# ---------------------------------------------------------------------------
# Tests: load_snapshot
# ---------------------------------------------------------------------------

class TestLoadSnapshot:
    def test_loads_by_path(self, snap_dir: Path):
        p = _make_snap(snap_dir, "SEM_A")
        data = load_snapshot(str(p))
        assert data["target"] == "SEM_A"

    def test_raises_on_missing(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_snapshot(str(tmp_path / "nonexistent.json"))


# ---------------------------------------------------------------------------
# Tests: format_timestamp
# ---------------------------------------------------------------------------

class TestFormatTimestamp:
    def test_formats_iso(self):
        result = format_timestamp("2025-06-15T14:30:45+00:00")
        assert "2025-06-15" in result
        assert "14:30:45" in result

    def test_handles_bad_input(self):
        result = format_timestamp("not-a-timestamp-abcdefghijklmn")
        # Should return first 19 chars as fallback
        assert result == "not-a-timestamp-abc"


# ---------------------------------------------------------------------------
# Tests: snapshot_summary
# ---------------------------------------------------------------------------

class TestSnapshotSummary:
    def test_deploy_icon(self):
        snap = {
            "timestamp": "2025-01-01T00:00:00+00:00",
            "action": "deploy",
            "target": "SEM_A",
            "new_state": {"sg": "x"},
        }
        result = snapshot_summary(snap)
        assert "🚀" in result
        assert "SEM_A" in result

    def test_revert_icon(self):
        snap = {
            "timestamp": "2025-01-01T00:00:00+00:00",
            "action": "revert",
            "target": "SEM_B",
            "new_state": {"qc": "y"},
        }
        result = snapshot_summary(snap)
        assert "⏪" in result

    def test_includes_field_names(self):
        snap = {
            "timestamp": "2025-01-01T00:00:00+00:00",
            "action": "deploy",
            "target": "X",
            "new_state": {"sql_generation": "val", "question_categorization": "val"},
        }
        result = snapshot_summary(snap)
        assert "sql_generation" in result
        assert "question_categorization" in result


# ---------------------------------------------------------------------------
# Tests: _prune_snapshots
# ---------------------------------------------------------------------------

class TestPruneSnapshots:
    def test_keeps_within_limit(self, snap_dir: Path):
        # Create more than the limit
        limit = 3
        with patch("snapshot_manager.MAX_SNAPSHOTS_PER_TARGET", limit):
            for i in range(5):
                _make_snap(snap_dir, "SEM_A", ts_suffix=f"{i:02d}")

            _prune_snapshots("SEM_A")
            remaining = list(snap_dir.glob("*_SEM_A.json"))
            assert len(remaining) == limit

    def test_does_not_prune_other_targets(self, snap_dir: Path):
        with patch("snapshot_manager.MAX_SNAPSHOTS_PER_TARGET", 2):
            for i in range(4):
                _make_snap(snap_dir, "SEM_A", ts_suffix=f"{i:02d}")
            _make_snap(snap_dir, "SEM_B", ts_suffix="10")
            _make_snap(snap_dir, "SEM_B", ts_suffix="11")

            _prune_snapshots("SEM_A")
            remaining_a = list(snap_dir.glob("*_SEM_A.json"))
            remaining_b = list(snap_dir.glob("*_SEM_B.json"))
            assert len(remaining_a) == 2
            assert len(remaining_b) == 2  # untouched
