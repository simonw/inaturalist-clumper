"""Read and write the clumps JSON file."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_existing(path: Path) -> dict[str, Any] | None:
    """Return the parsed JSON file, or None if it doesn't exist."""
    if not path.exists():
        return None
    return json.loads(path.read_text())


def extract_observations(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten all observations out of every clump in a loaded state."""
    return [obs for clump in state.get("clumps", []) for obs in clump.get("observations", [])]


def max_id_by_user(observations: list[dict[str, Any]]) -> dict[str, int]:
    """Per-user highest observation id seen."""
    out: dict[str, int] = {}
    for obs in observations:
        login = obs["user_login"]
        if obs["id"] > out.get(login, 0):
            out[login] = obs["id"]
    return out


def merge_observations(
    existing: list[dict[str, Any]],
    fresh: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Combine two observation lists, deduping by id. Fresh records win on conflict."""
    by_id: dict[int, dict[str, Any]] = {o["id"]: o for o in existing}
    for o in fresh:
        by_id[o["id"]] = o
    return list(by_id.values())


def write_output(
    path: Path,
    *,
    users: list[str],
    params: dict[str, float],
    total_observations: int,
    skipped_no_time_or_location: int,
    clumps: list[dict[str, Any]],
) -> None:
    """Write the JSON output file."""
    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "users": users,
        "params": params,
        "total_observations": total_observations,
        "skipped_no_time_or_location": skipped_no_time_or_location,
        "total_clumps": len(clumps),
        "clumps": clumps,
    }
    path.write_text(json.dumps(payload, indent=2))
