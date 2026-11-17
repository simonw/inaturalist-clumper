"""Group normalised observations into clumps by space + time."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from math import asin, cos, floor, radians, sin, sqrt
from typing import Any, Mapping

EARTH_RADIUS_KM = 6371.0

# iNaturalist obscures a location by replacing it with a random point inside
# the 0.2 x 0.2 degree grid cell that contains the true coordinates.
OBSCURED_CELLS_PER_DEGREE = 5


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in kilometres."""
    rlat1, rlat2 = radians(lat1), radians(lat2)
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def _axis_range(value: float, obscured: bool) -> tuple[float, float]:
    """The range of values the true coordinate could have on one axis."""
    if not obscured:
        return (value, value)
    low = floor(value * OBSCURED_CELLS_PER_DEGREE)
    return (low / OBSCURED_CELLS_PER_DEGREE, (low + 1) / OBSCURED_CELLS_PER_DEGREE)


def _closest(a: tuple[float, float], b: tuple[float, float]) -> tuple[float, float]:
    """The closest pair of values from two ranges - identical if they overlap."""
    if a[1] < b[0]:
        return (a[1], b[0])
    if b[1] < a[0]:
        return (a[0], b[1])
    shared = max(a[0], b[0])
    return (shared, shared)


def clump_distance_km(a: Mapping[str, Any], b: Mapping[str, Any]) -> float:
    """Distance between two observations for the purpose of clumping.

    The published coordinates of an obscured observation are a random point in
    its 0.2 degree grid cell, so they say nothing about where in that cell it
    really was. An obscured observation is therefore assumed to be in the same
    location as the other observation whenever that is possible: the distance
    is measured from the nearest point of its cell, and is zero if the other
    observation is inside that cell (or is obscured to the same cell).
    """
    lat_a, lat_b = _closest(
        _axis_range(a["latitude"], bool(a.get("obscured"))),
        _axis_range(b["latitude"], bool(b.get("obscured"))),
    )
    lon_a, lon_b = _closest(
        _axis_range(a["longitude"], bool(a.get("obscured"))),
        _axis_range(b["longitude"], bool(b.get("obscured"))),
    )
    return haversine_km(lat_a, lon_a, lat_b, lon_b)


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


def _mode_place_guess(observations: list[dict[str, Any]]) -> str | None:
    """Pick the most common non-empty place_guess among eligible observations.

    Eligible = not obscured and no geoprivacy set, so we don't promote a leaked
    private location. Ties broken by the most recent observation.
    """
    eligible = [
        o for o in observations
        if not o.get("obscured") and not o.get("geoprivacy") and o.get("place_guess")
    ]
    if not eligible:
        return None
    counts: Counter[str] = Counter()
    latest: dict[str, str] = {}
    for o in eligible:
        guess = o["place_guess"]
        counts[guess] += 1
        latest[guess] = max(latest.get(guess, ""), o["observed_at"])
    return max(counts, key=lambda g: (counts[g], latest[g]))


def _most_specific_shared_place(
    observations: list[dict[str, Any]],
    places_lookup: Mapping[int, Mapping[str, Any]],
) -> int | None:
    """Intersect place_ids across observations and return the deepest in the hierarchy."""
    place_id_sets = [set(o.get("place_ids") or []) for o in observations]
    if not place_id_sets or not all(place_id_sets):
        return None
    shared = set.intersection(*place_id_sets)
    if not shared:
        return None
    # Pick the place whose ancestor_ids ⊇ (shared \ {self}) — the deepest in the chain.
    candidates = []
    for pid in shared:
        info = places_lookup.get(pid)
        if not info:
            continue
        ancestors = set(info.get("ancestor_ids") or [])
        if shared - {pid} <= ancestors:
            candidates.append(pid)
    if not candidates:
        # Fallback: longest ancestor list among those we know about.
        known = [pid for pid in shared if pid in places_lookup]
        if not known:
            return None
        return max(known, key=lambda pid: (len(places_lookup[pid].get("ancestor_ids") or []), -pid))
    return max(candidates, key=lambda pid: (len(places_lookup[pid].get("ancestor_ids") or []), -pid))


def _build_location(
    observations: list[dict[str, Any]],
    places_lookup: Mapping[int, Mapping[str, Any]] | None,
) -> dict[str, Any] | None:
    place_guess = _mode_place_guess(observations)
    place_id: int | None = None
    display_name: str | None = None
    breadcrumb: list[int] | None = None

    if places_lookup is not None:
        place_id = _most_specific_shared_place(observations, places_lookup)
        if place_id is not None:
            info = places_lookup[place_id]
            display_name = info.get("display_name")
            breadcrumb = [place_id, *reversed(info.get("ancestor_ids") or [])]

    if place_guess is None and place_id is None:
        return None

    location: dict[str, Any] = {"place_guess": place_guess}
    if places_lookup is not None:
        location["place_id"] = place_id
        location["display_name"] = display_name
        location["breadcrumb"] = breadcrumb
    return location


def _build_clump_metadata(
    observations: list[dict[str, Any]],
    places_lookup: Mapping[int, Mapping[str, Any]] | None,
) -> dict[str, Any]:
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

    metadata: dict[str, Any] = {
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
    location = _build_location(obs_sorted, places_lookup)
    if location is not None:
        metadata["location"] = location
    return metadata


def build_clumps(
    observations: list[dict[str, Any]],
    *,
    max_distance_km: float,
    max_hours: float,
    places_lookup: Mapping[int, Mapping[str, Any]] | None = None,
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
            d = clump_distance_km(observations[i], observations[j])
            if d <= max_distance_km:
                uf.union(i, j)

    groups: dict[int, list[dict[str, Any]]] = {}
    for i, obs in enumerate(observations):
        groups.setdefault(uf.find(i), []).append(obs)

    clumps = [_build_clump_metadata(group, places_lookup) for group in groups.values()]
    clumps.sort(key=lambda c: c["started_at"])
    for c in clumps:
        c["id"] = min(o["id"] for o in c["observations"])
    return [{"id": c.pop("id"), **c} for c in clumps]
