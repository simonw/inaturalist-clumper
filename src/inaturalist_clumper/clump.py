"""Group normalised observations into clumps by space + time."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from typing import Any

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in kilometres."""
    rlat1, rlat2 = radians(lat1), radians(lat2)
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))

    def find(self, i: int) -> int:
        while self.parent[i] != i:
            self.parent[i] = self.parent[self.parent[i]]
            i = self.parent[i]
        return i

    def union(self, i: int, j: int) -> None:
        ri, rj = self.find(i), self.find(j)
        if ri != rj:
            self.parent[ri] = rj


def _parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _round(x: float, ndigits: int = 6) -> float:
    return round(x, ndigits)


def _build_clump_metadata(observations: list[dict[str, Any]]) -> dict[str, Any]:
    obs_sorted = sorted(observations, key=lambda o: o["observed_at"])
    started = obs_sorted[0]["observed_at"]
    ended = obs_sorted[-1]["observed_at"]
    duration_hours = (_parse_dt(ended) - _parse_dt(started)).total_seconds() / 3600.0

    lats = [o["latitude"] for o in obs_sorted]
    lons = [o["longitude"] for o in obs_sorted]
    centroid = [_round(sum(lats) / len(lats)), _round(sum(lons) / len(lons))]
    bbox = [[_round(min(lats)), _round(min(lons))], [_round(max(lats)), _round(max(lons))]]
    span_km = haversine_km(min(lats), min(lons), max(lats), max(lons))

    counter: Counter[tuple[str | None, str | None]] = Counter()
    for o in obs_sorted:
        taxon = o.get("taxon")
        if taxon:
            key = (taxon.get("scientific_name"), taxon.get("common_name"))
        else:
            key = (None, o.get("species_guess"))
        counter[key] += 1
    species = [
        {"scientific_name": sci, "common_name": com, "count": n}
        for (sci, com), n in counter.most_common()
    ]

    return {
        "started_at": started,
        "ended_at": ended,
        "duration_hours": round(duration_hours, 4),
        "centroid": centroid,
        "bbox": bbox,
        "span_km": round(span_km, 4),
        "observation_count": len(obs_sorted),
        "species": species,
        "observations": obs_sorted,
    }


def build_clumps(
    observations: list[dict[str, Any]],
    *,
    max_distance_km: float,
    max_hours: float,
) -> list[dict[str, Any]]:
    """Cluster observations by single-link in space + time."""
    n = len(observations)
    uf = _UnionFind(n)

    parsed = [_parse_dt(o["observed_at"]) for o in observations]
    max_seconds = max_hours * 3600.0

    for i in range(n):
        for j in range(i + 1, n):
            if abs((parsed[j] - parsed[i]).total_seconds()) > max_seconds:
                continue
            d = haversine_km(
                observations[i]["latitude"], observations[i]["longitude"],
                observations[j]["latitude"], observations[j]["longitude"],
            )
            if d <= max_distance_km:
                uf.union(i, j)

    groups: dict[int, list[dict[str, Any]]] = {}
    for i, obs in enumerate(observations):
        groups.setdefault(uf.find(i), []).append(obs)

    clumps = [_build_clump_metadata(group) for group in groups.values()]
    clumps.sort(key=lambda c: c["started_at"])
    for n, c in enumerate(clumps, start=1):
        c["id"] = n
    return [{"id": c.pop("id"), **c} for c in clumps]
