"""HTTP client for the iNaturalist v1 API."""

from __future__ import annotations

import time
from typing import Any

import httpx

BASE_URL = "https://api.inaturalist.org/v1/observations"
USER_AGENT = "inaturalist-clumper/0.1 (+https://github.com/simonw/inaturalist-clumper)"
PER_PAGE = 200


def fetch_user_observations(
    login: str,
    *,
    id_above: int = 0,
    sleep_seconds: float = 1.0,
) -> list[dict[str, Any]]:
    """Fetch all observations for one user, optionally only those above a given id.

    Pages by id_above to stay compatible with iNaturalist's recommended
    cursor-style pagination. Sleeps between requests to stay under their
    60 req/min recommended rate limit.
    """
    results: list[dict[str, Any]] = []
    cursor = id_above
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(headers=headers, timeout=30.0) as client:
        while True:
            params = {
                "user_login": login,
                "per_page": PER_PAGE,
                "order_by": "id",
                "order": "asc",
                "id_above": cursor,
            }
            response = client.get(BASE_URL, params=params)
            response.raise_for_status()
            page = response.json().get("results", [])
            results.extend(page)
            if len(page) < PER_PAGE:
                break
            cursor = page[-1]["id"]
            if sleep_seconds:
                time.sleep(sleep_seconds)
    return results
