"""
Deployment snapshot manager.

Captures Snowflake state before each deploy, enabling reliable revert
to any previous deployment point.

Snapshots are stored as JSON files in .snapshots/ (git-ignored).
Each snapshot records the previous and new instruction state for a target.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_DIR = REPO_ROOT / ".snapshots"

# Keep at most this many snapshots per target
MAX_SNAPSHOTS_PER_TARGET = 50


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_snapshot(
    target_type: str,
    target: str,
    previous_state: Dict[str, str],
    new_state: Dict[str, str],
    action: str = "deploy",
) -> Path:
    """Save a pre-deploy snapshot and return the file path.

    Parameters
    ----------
    target_type : str
        ``"Semantic View"`` or ``"Agent"``.
    target : str
        Target name, e.g. ``"SEM_INSULINTEL"`` or ``"INSULINTEL"``.
    previous_state : dict
        Field values *before* this deploy (fetched from Snowflake).
    new_state : dict
        Field values being deployed.
    action : str
        ``"deploy"`` or ``"revert"`` — labels the snapshot for history.
    """
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc)
    label = ts.strftime("%Y%m%dT%H%M%SZ")

    snapshot = {
        "timestamp": ts.isoformat(),
        "target_type": target_type,
        "target": target,
        "action": action,
        "previous_state": previous_state,
        "new_state": new_state,
    }

    filename = f"{label}_{target}.json"
    path = SNAPSHOT_DIR / filename
    path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")

    # Prune old snapshots for this target
    _prune_snapshots(target)

    return path


# ---------------------------------------------------------------------------
# Read / list
# ---------------------------------------------------------------------------

def list_snapshots(target: Optional[str] = None, limit: int = 20) -> List[dict]:
    """List snapshots, most recent first. Optionally filtered by target."""
    if not SNAPSHOT_DIR.exists():
        return []

    snapshots: List[dict] = []
    for path in sorted(SNAPSHOT_DIR.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["_path"] = str(path)
            data["_filename"] = path.name
            if target is None or data.get("target") == target:
                snapshots.append(data)
        except (json.JSONDecodeError, KeyError):
            continue

    return snapshots[:limit]


def get_latest_snapshot(target: str) -> Optional[dict]:
    """Get the most recent snapshot for a target (any action type)."""
    snaps = list_snapshots(target, limit=1)
    return snaps[0] if snaps else None


def load_snapshot(path: str) -> dict:
    """Load a specific snapshot by file path."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# History display helpers
# ---------------------------------------------------------------------------

def format_timestamp(iso_ts: str) -> str:
    """Format an ISO timestamp for display."""
    try:
        dt = datetime.fromisoformat(iso_ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, TypeError):
        return iso_ts[:19]


def snapshot_summary(snap: dict) -> str:
    """One-line summary of a snapshot for display."""
    ts = format_timestamp(snap.get("timestamp", ""))
    action = snap.get("action", "deploy")
    target = snap.get("target", "?")
    icon = "🚀" if action == "deploy" else "⏪"
    fields = ", ".join(snap.get("new_state", {}).keys())
    return f"{icon} {ts} — {action.title()} {target} ({fields})"


# ---------------------------------------------------------------------------
# Prune
# ---------------------------------------------------------------------------

def _prune_snapshots(target: str) -> None:
    """Keep only the most recent MAX_SNAPSHOTS_PER_TARGET for a target."""
    if not SNAPSHOT_DIR.exists():
        return

    target_files = sorted(
        [p for p in SNAPSHOT_DIR.glob(f"*_{target}.json")],
        reverse=True,
    )

    for old_file in target_files[MAX_SNAPSHOTS_PER_TARGET:]:
        try:
            old_file.unlink()
        except OSError:
            pass
