"""HTTP client for the iNaturalist v1 places endpoint."""

from __future__ import annotations

import time
from typing import Any, Iterable

import httpx

from .api import USER_AGENT

PLACES_BASE_URL = "https://api.inaturalist.org/v1/places"
BATCH_SIZE = 30


def _normalize_place(p: dict[str, Any]) -> dict[str, Any]:
    pid = p["id"]
    ancestors = [a for a in (p.get("ancestor_place_ids") or []) if a != pid]
    return {
        "name": p.get("name"),
        "display_name": p.get("display_name"),
        "admin_level": p.get("admin_level"),
        "place_type": p.get("place_type"),
        "ancestor_ids": ancestors,
    }


def fetch_places(
    place_ids: Iterable[int],
    *,
    sleep_seconds: float = 1.0,
) -> dict[int, dict[str, Any]]:
    """Fetch place metadata for the given iNat place IDs.

    Dedupes and batches in groups of BATCH_SIZE to stay within URL length and
    iNat's rate limits. Returns {place_id: normalized_record}.
    """
    unique = sorted({int(pid) for pid in place_ids})
    if not unique:
        return {}

    out: dict[int, dict[str, Any]] = {}
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, timeout=30.0) as client:
        for i in range(0, len(unique), BATCH_SIZE):
            batch = unique[i : i + BATCH_SIZE]
            ids_param = ",".join(str(p) for p in batch)
            response = client.get(f"{PLACES_BASE_URL}/{ids_param}")
            response.raise_for_status()
            for p in response.json().get("results", []):
                out[p["id"]] = _normalize_place(p)
            if sleep_seconds and i + BATCH_SIZE < len(unique):
                time.sleep(sleep_seconds)
    return out
