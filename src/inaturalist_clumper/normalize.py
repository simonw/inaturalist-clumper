"""Flatten raw iNaturalist observation dicts into our compact record format."""

from __future__ import annotations

import re
from typing import Any

_SQUARE_RE = re.compile(r"/square\.(jpe?g|png)$", re.IGNORECASE)


def _photo_url(square_url: str, size: str) -> str:
    return _SQUARE_RE.sub(f"/{size}.\\1", square_url)


def _normalize_photo(photo: dict[str, Any]) -> dict[str, Any]:
    url = photo["url"]
    return {
        "id": photo["id"],
        "thumbnail_url": _photo_url(url, "medium"),
        "large_url": _photo_url(url, "large"),
        "original_url": _photo_url(url, "original"),
        "original_dimensions": photo.get("original_dimensions"),
        "attribution": photo.get("attribution"),
        "license_code": photo.get("license_code"),
    }


def _normalize_taxon(taxon: dict[str, Any] | None) -> dict[str, Any] | None:
    if not taxon:
        return None
    return {
        "id": taxon.get("id"),
        "scientific_name": taxon.get("name"),
        "common_name": taxon.get("preferred_common_name"),
        "rank": taxon.get("rank"),
    }


def normalize(obs: dict[str, Any], *, user_login: str) -> dict[str, Any] | None:
    """Flatten one iNaturalist observation. Returns None if it can't be clumped."""
    time_observed_at = obs.get("time_observed_at")
    geojson = obs.get("geojson")
    if not time_observed_at or not geojson:
        return None

    lon, lat = geojson["coordinates"]

    return {
        "id": obs["id"],
        "uri": obs.get("uri"),
        "user_login": user_login,
        "observed_at": time_observed_at,
        "latitude": lat,
        "longitude": lon,
        "positional_accuracy_m": obs.get("positional_accuracy"),
        "obscured": obs.get("obscured", False),
        "geoprivacy": obs.get("geoprivacy"),
        "place_guess": obs.get("place_guess"),
        "place_ids": list(obs.get("place_ids") or []),
        "taxon": _normalize_taxon(obs.get("taxon")),
        "species_guess": obs.get("species_guess"),
        "photos": [_normalize_photo(p) for p in obs.get("photos", [])],
    }
