import json

from inaturalist_clumper.store import (
    extract_observations,
    extract_places_cache,
    load_existing,
    max_id_by_user,
    merge_observations,
    prune_places_to_breadcrumbs,
    write_output,
)


def _seeded_clumps_file(tmp_path):
    payload = {
        "generated_at": "2026-05-01T00:00:00Z",
        "users": ["simon583", "simonw"],
        "params": {"max_distance_km": 5.0, "max_hours": 3.0},
        "total_observations": 3,
        "skipped_no_time_or_location": 0,
        "total_clumps": 1,
        "clumps": [
            {
                "id": 1,
                "started_at": "2025-01-01T10:00:00+00:00",
                "ended_at": "2025-01-01T11:30:00+00:00",
                "duration_hours": 1.5,
                "centroid": [37.0, -122.0],
                "bbox": [[37.0, -122.0], [37.0, -122.0]],
                "span_km": 0.0,
                "observation_count": 3,
                "species": [],
                "observations": [
                    {"id": 100, "user_login": "simonw", "observed_at": "2025-01-01T10:00:00+00:00"},
                    {"id": 200, "user_login": "simon583", "observed_at": "2025-01-01T10:30:00+00:00"},
                    {"id": 300, "user_login": "simonw", "observed_at": "2025-01-01T11:30:00+00:00"},
                ],
            }
        ],
    }
    path = tmp_path / "clumps.json"
    path.write_text(json.dumps(payload))
    return path, payload


def test_load_returns_none_when_file_missing(tmp_path):
    assert load_existing(tmp_path / "missing.json") is None


def test_load_parses_existing_file(tmp_path):
    path, payload = _seeded_clumps_file(tmp_path)
    assert load_existing(path) == payload


def test_extract_observations_flattens_clumps(tmp_path):
    _, payload = _seeded_clumps_file(tmp_path)
    observations = extract_observations(payload)
    assert [o["id"] for o in observations] == [100, 200, 300]


def test_max_id_by_user_per_login():
    observations = [
        {"id": 100, "user_login": "simonw"},
        {"id": 300, "user_login": "simonw"},
        {"id": 250, "user_login": "simonw"},
        {"id": 200, "user_login": "simon583"},
    ]
    assert max_id_by_user(observations) == {"simonw": 300, "simon583": 200}


def test_max_id_by_user_empty():
    assert max_id_by_user([]) == {}


def test_merge_dedupes_by_id_fresh_wins():
    existing = [
        {"id": 1, "observed_at": "old"},
        {"id": 2, "observed_at": "old"},
    ]
    fresh = [
        {"id": 2, "observed_at": "new"},
        {"id": 3, "observed_at": "new"},
    ]
    merged = merge_observations(existing, fresh)
    by_id = {o["id"]: o for o in merged}
    assert set(by_id) == {1, 2, 3}
    assert by_id[2]["observed_at"] == "new"
    assert by_id[1]["observed_at"] == "old"


def test_write_then_load_roundtrip(tmp_path):
    path = tmp_path / "out.json"
    write_output(
        path,
        users=["simonw"],
        params={"max_distance_km": 5.0, "max_hours": 3.0},
        total_observations=2,
        skipped_no_time_or_location=1,
        clumps=[{"id": 1, "started_at": "2025-01-01T10:00:00+00:00", "observations": []}],
        places={"12": {"name": "X", "display_name": "X", "ancestor_ids": []}},
    )
    loaded = load_existing(path)
    assert loaded["users"] == ["simonw"]
    assert loaded["params"] == {"max_distance_km": 5.0, "max_hours": 3.0}
    assert loaded["total_observations"] == 2
    assert loaded["skipped_no_time_or_location"] == 1
    assert loaded["total_clumps"] == 1
    assert "generated_at" in loaded
    assert loaded["clumps"][0]["id"] == 1
    assert loaded["places"] == {"12": {"name": "X", "display_name": "X", "ancestor_ids": []}}


def test_write_omits_places_when_empty(tmp_path):
    path = tmp_path / "out.json"
    write_output(
        path,
        users=["simonw"],
        params={"max_distance_km": 5.0, "max_hours": 3.0},
        total_observations=0,
        skipped_no_time_or_location=0,
        clumps=[],
        places={},
    )
    loaded = load_existing(path)
    assert "places" not in loaded


def test_extract_places_cache_returns_int_keyed_dict():
    state = {
        "places": {
            "12": {"name": "County", "display_name": "County, US", "ancestor_ids": [1, 11]},
            "1": {"name": "US", "display_name": "US", "ancestor_ids": []},
        }
    }
    cache = extract_places_cache(state)
    assert cache == {
        12: {"name": "County", "display_name": "County, US", "ancestor_ids": [1, 11]},
        1: {"name": "US", "display_name": "US", "ancestor_ids": []},
    }


def test_extract_places_cache_missing_returns_empty_dict():
    assert extract_places_cache({}) == {}


def test_prune_places_to_breadcrumbs_keeps_only_referenced():
    cache = {
        12: {"name": "County", "ancestor_ids": [1, 11]},
        11: {"name": "State", "ancestor_ids": [1]},
        1: {"name": "US", "ancestor_ids": []},
        999: {"name": "Unused", "ancestor_ids": []},
    }
    clumps = [
        {"location": {"breadcrumb": [12, 11, 1]}},
        {"location": {"breadcrumb": None}},
        {"location": {"place_guess": "x"}},  # no breadcrumb key
        {},  # no location at all
    ]
    pruned = prune_places_to_breadcrumbs(cache, clumps)
    assert set(pruned) == {12, 11, 1}
