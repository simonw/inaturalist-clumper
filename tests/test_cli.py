import json

import pytest

from inaturalist_clumper.cli import main


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _seconds: None)


def _raw_observation(obs_id, observed_at, lat=37.0, lon=-122.0, login_in_uri="simonw"):
    return {
        "id": obs_id,
        "uri": f"https://www.inaturalist.org/observations/{obs_id}",
        "time_observed_at": observed_at,
        "geojson": {"type": "Point", "coordinates": [lon, lat]},
        "positional_accuracy": 5,
        "obscured": False,
        "geoprivacy": None,
        "species_guess": "Snowy Egret",
        "taxon": {
            "id": 4940,
            "name": "Egretta thula",
            "preferred_common_name": "Snowy Egret",
            "rank": "species",
        },
        "photos": [
            {
                "id": obs_id * 10,
                "license_code": "cc-by-nc",
                "url": f"https://inaturalist-open-data.s3.amazonaws.com/photos/{obs_id * 10}/square.jpg",
                "attribution": "x",
            }
        ],
    }


def test_first_run_writes_clumps_json(httpx_mock, tmp_path):
    httpx_mock.add_response(
        json={
            "results": [
                _raw_observation(1, "2025-03-15T08:47:39-07:00"),
                _raw_observation(2, "2025-03-15T09:00:00-07:00"),
            ]
        }
    )
    output = tmp_path / "out.json"

    main(["simonw", "--output", str(output)])

    data = json.loads(output.read_text())
    assert data["users"] == ["simonw"]
    assert data["params"] == {"max_distance_km": 5.0, "max_hours": 3.0}
    assert data["total_observations"] == 2
    assert data["total_clumps"] == 1
    obs_ids = [o["id"] for o in data["clumps"][0]["observations"]]
    assert obs_ids == [1, 2]
    assert data["clumps"][0]["observations"][0]["user_login"] == "simonw"


def test_second_run_uses_updated_since_from_generated_at(httpx_mock, tmp_path):
    output = tmp_path / "out.json"
    seed = {
        "generated_at": "2026-05-01T00:00:00Z",
        "users": ["simonw"],
        "params": {"max_distance_km": 5.0, "max_hours": 3.0},
        "total_observations": 1,
        "skipped_no_time_or_location": 0,
        "total_clumps": 1,
        "clumps": [
            {
                "id": 1,
                "started_at": "2025-01-01T10:00:00+00:00",
                "ended_at": "2025-01-01T10:00:00+00:00",
                "duration_hours": 0.0,
                "centroid": [37.0, -122.0],
                "bbox": [[37.0, -122.0], [37.0, -122.0]],
                "span_km": 0.0,
                "observation_count": 1,
                "species": [],
                "observations": [
                    {
                        "id": 500,
                        "uri": "https://www.inaturalist.org/observations/500",
                        "user_login": "simonw",
                        "observed_at": "2025-01-01T10:00:00+00:00",
                        "latitude": 37.0,
                        "longitude": -122.0,
                        "positional_accuracy_m": 5,
                        "obscured": False,
                        "geoprivacy": None,
                        "taxon": None,
                        "species_guess": "Cat",
                        "photos": [],
                    }
                ],
            }
        ],
    }
    output.write_text(json.dumps(seed))
    httpx_mock.add_response(json={"results": []})

    main(["simonw", "--output", str(output)])

    request = httpx_mock.get_requests()[0]
    assert request.url.params["updated_since"] == "2026-05-01T00:00:00Z"
    assert request.url.params["user_login"] == "simonw"

    # Existing observation should still be in the output
    data = json.loads(output.read_text())
    assert data["total_observations"] == 1
    assert data["clumps"][0]["observations"][0]["id"] == 500


def test_edited_observation_is_replaced_on_second_run(httpx_mock, tmp_path):
    output = tmp_path / "out.json"
    seed = {
        "generated_at": "2026-05-01T00:00:00Z",
        "users": ["simonw"],
        "params": {"max_distance_km": 5.0, "max_hours": 3.0},
        "total_observations": 1,
        "skipped_no_time_or_location": 0,
        "total_clumps": 1,
        "clumps": [
            {
                "id": 1,
                "started_at": "2025-01-01T10:00:00+00:00",
                "ended_at": "2025-01-01T10:00:00+00:00",
                "duration_hours": 0.0,
                "centroid": [37.0, -122.0],
                "bbox": [[37.0, -122.0], [37.0, -122.0]],
                "span_km": 0.0,
                "observation_count": 1,
                "species": [],
                "observations": [
                    {
                        "id": 500,
                        "uri": "https://www.inaturalist.org/observations/500",
                        "user_login": "simonw",
                        "observed_at": "2025-01-01T10:00:00+00:00",
                        "latitude": 37.0,
                        "longitude": -122.0,
                        "positional_accuracy_m": 5,
                        "obscured": False,
                        "geoprivacy": None,
                        "taxon": None,
                        "species_guess": "Old Guess",
                        "photos": [],
                    }
                ],
            }
        ],
    }
    output.write_text(json.dumps(seed))
    # Server returns the same observation with an edited species_guess
    edited = _raw_observation(500, "2025-01-01T10:00:00+00:00")
    edited["species_guess"] = "Corrected Guess"
    httpx_mock.add_response(json={"results": [edited]})

    main(["simonw", "--output", str(output)])

    data = json.loads(output.read_text())
    assert data["total_observations"] == 1
    assert data["clumps"][0]["observations"][0]["id"] == 500
    assert data["clumps"][0]["observations"][0]["species_guess"] == "Corrected Guess"


def test_first_run_does_not_use_updated_since(httpx_mock, tmp_path):
    httpx_mock.add_response(json={"results": []})
    output = tmp_path / "out.json"

    main(["simonw", "--output", str(output)])

    request = httpx_mock.get_requests()[0]
    assert "updated_since" not in request.url.params


def test_full_refresh_ignores_existing_state(httpx_mock, tmp_path):
    output = tmp_path / "out.json"
    output.write_text(
        json.dumps(
            {
                "generated_at": "2026-05-01T00:00:00Z",
                "clumps": [
                    {
                        "observations": [
                            {
                                "id": 999,
                                "user_login": "simonw",
                                "observed_at": "2025-01-01T10:00:00+00:00",
                                "latitude": 37.0,
                                "longitude": -122.0,
                            }
                        ]
                    }
                ],
            }
        )
    )
    httpx_mock.add_response(json={"results": []})

    main(["simonw", "--output", str(output), "--full-refresh"])

    request = httpx_mock.get_requests()[0]
    assert request.url.params["id_above"] == "0"
    assert "updated_since" not in request.url.params
    # Existing observation should be discarded
    data = json.loads(output.read_text())
    assert data["total_observations"] == 0


def test_multiple_users_share_updated_since(httpx_mock, tmp_path):
    output = tmp_path / "out.json"
    seed = {
        "generated_at": "2026-04-01T00:00:00Z",
        "clumps": [
            {
                "observations": [
                    {
                        "id": 10,
                        "user_login": "simon583",
                        "observed_at": "2025-01-01T10:00:00+00:00",
                        "latitude": 37.0,
                        "longitude": -122.0,
                    },
                    {
                        "id": 500,
                        "user_login": "simonw",
                        "observed_at": "2025-01-02T10:00:00+00:00",
                        "latitude": 37.0,
                        "longitude": -122.0,
                    },
                ]
            }
        ],
    }
    output.write_text(json.dumps(seed))
    httpx_mock.add_response(json={"results": []})  # simon583
    httpx_mock.add_response(json={"results": []})  # simonw

    main(["simon583", "simonw", "--output", str(output)])

    requests = httpx_mock.get_requests()
    by_login = {
        r.url.params["user_login"]: r.url.params["updated_since"] for r in requests
    }
    assert by_login == {
        "simon583": "2026-04-01T00:00:00Z",
        "simonw": "2026-04-01T00:00:00Z",
    }


def test_distance_and_hours_flags_are_respected(httpx_mock, tmp_path):
    httpx_mock.add_response(
        json={
            "results": [
                _raw_observation(1, "2025-01-01T10:00:00+00:00", lat=37.0),
                _raw_observation(2, "2025-01-01T10:30:00+00:00", lat=37.05),  # ~5.5 km
            ]
        }
    )
    output = tmp_path / "out.json"

    main(["simonw", "--output", str(output), "--distance-km", "1", "--hours", "3"])

    data = json.loads(output.read_text())
    assert data["params"] == {"max_distance_km": 1.0, "max_hours": 3.0}
    # 5.5 km apart is over 1 km threshold → two clumps
    assert data["total_clumps"] == 2


def _place(pid, name, ancestors):
    return {
        "id": pid,
        "name": name,
        "display_name": f"{name} display",
        "admin_level": None,
        "place_type": None,
        "ancestor_place_ids": [*ancestors, pid],
    }


def test_first_run_populates_location_on_clumps(httpx_mock, tmp_path):
    obs1 = _raw_observation(1, "2025-03-15T08:47:39-07:00")
    obs1["place_guess"] = "Pescadero State Beach"
    obs1["place_ids"] = [97394, 12, 11, 1]
    obs2 = _raw_observation(2, "2025-03-15T09:00:00-07:00")
    obs2["place_guess"] = "Pescadero State Beach"
    obs2["place_ids"] = [97394, 12, 11, 1]

    httpx_mock.add_response(json={"results": [obs1, obs2]})
    httpx_mock.add_response(
        json={
            "results": [
                _place(1, "US", []),
                _place(11, "California", [1]),
                _place(12, "San Mateo County", [1, 11]),
                _place(97394, "Pescadero State Beach", [1, 11, 12]),
            ]
        }
    )
    output = tmp_path / "out.json"

    main(["simonw", "--output", str(output)])

    data = json.loads(output.read_text())
    clump = data["clumps"][0]
    assert clump["location"]["place_guess"] == "Pescadero State Beach"
    assert clump["location"]["place_id"] == 97394
    assert clump["location"]["display_name"] == "Pescadero State Beach display"
    assert clump["location"]["breadcrumb"] == [97394, 12, 11, 1]
    assert set(data["places"]) == {"1", "11", "12", "97394"}


def test_no_place_request_when_observations_have_no_place_ids(httpx_mock, tmp_path):
    httpx_mock.add_response(
        json={"results": [_raw_observation(1, "2025-03-15T08:47:39-07:00")]}
    )
    output = tmp_path / "out.json"

    main(["simonw", "--output", str(output)])

    # Only the observations request should have been made.
    assert len(httpx_mock.get_requests()) == 1
    data = json.loads(output.read_text())
    assert "places" not in data


def test_places_cache_pruned_to_breadcrumb_ids(httpx_mock, tmp_path):
    # Observation lists a "neighborhood" place that won't end up in any breadcrumb.
    obs1 = _raw_observation(1, "2025-03-15T08:47:39-07:00")
    obs1["place_ids"] = [12, 11, 1]
    obs2 = _raw_observation(2, "2025-03-15T09:00:00-07:00")
    obs2["place_ids"] = [99, 11, 1]  # different sub-place — intersection drops both

    httpx_mock.add_response(json={"results": [obs1, obs2]})
    httpx_mock.add_response(
        json={
            "results": [
                _place(1, "US", []),
                _place(11, "California", [1]),
                _place(12, "Place A", [1, 11]),
                _place(99, "Place B", [1, 11]),
            ]
        }
    )
    output = tmp_path / "out.json"

    main(["simonw", "--output", str(output)])

    data = json.loads(output.read_text())
    assert data["clumps"][0]["location"]["place_id"] == 11  # shared ancestor
    assert set(data["places"]) == {"1", "11"}  # 12 and 99 pruned


def test_second_run_reuses_cached_places_without_refetching(httpx_mock, tmp_path):
    output = tmp_path / "out.json"
    seed = {
        "generated_at": "2026-05-01T00:00:00Z",
        "users": ["simonw"],
        "params": {"max_distance_km": 5.0, "max_hours": 3.0},
        "total_observations": 1,
        "skipped_no_time_or_location": 0,
        "total_clumps": 1,
        "places": {
            "1": {"name": "US", "display_name": "US", "admin_level": 0, "ancestor_ids": []},
            "11": {"name": "California", "display_name": "California, US", "admin_level": 10, "ancestor_ids": [1]},
            "12": {"name": "County", "display_name": "County, US", "admin_level": 20, "ancestor_ids": [1, 11]},
        },
        "clumps": [
            {
                "id": 500,
                "started_at": "2025-01-01T10:00:00+00:00",
                "ended_at": "2025-01-01T10:00:00+00:00",
                "duration_hours": 0.0,
                "centroid": [37.0, -122.0],
                "bbox": [[37.0, -122.0], [37.0, -122.0]],
                "span_km": 0.0,
                "observation_count": 1,
                "species": [],
                "location": {
                    "place_guess": "Old", "place_id": 12,
                    "display_name": "County, US", "breadcrumb": [12, 11, 1],
                },
                "observations": [
                    {
                        "id": 500,
                        "uri": "https://www.inaturalist.org/observations/500",
                        "user_login": "simonw",
                        "observed_at": "2025-01-01T10:00:00+00:00",
                        "latitude": 37.0,
                        "longitude": -122.0,
                        "positional_accuracy_m": 5,
                        "obscured": False,
                        "geoprivacy": None,
                        "place_guess": "Old",
                        "place_ids": [12, 11, 1],
                        "taxon": None,
                        "species_guess": "Cat",
                        "photos": [],
                    }
                ],
            }
        ],
    }
    output.write_text(json.dumps(seed))
    httpx_mock.add_response(json={"results": []})  # observations only

    main(["simonw", "--output", str(output)])

    # No /places/ request — cache was complete.
    assert len(httpx_mock.get_requests()) == 1
    data = json.loads(output.read_text())
    assert data["clumps"][0]["location"]["place_id"] == 12
    assert set(data["places"]) == {"1", "11", "12"}


def test_second_run_fetches_only_missing_place_ids(httpx_mock, tmp_path):
    output = tmp_path / "out.json"
    seed = {
        "generated_at": "2026-05-01T00:00:00Z",
        "users": ["simonw"],
        "params": {"max_distance_km": 5.0, "max_hours": 3.0},
        "total_observations": 1,
        "skipped_no_time_or_location": 0,
        "total_clumps": 1,
        "places": {
            "1": {"name": "US", "display_name": "US", "ancestor_ids": []},
            "11": {"name": "California", "display_name": "California, US", "ancestor_ids": [1]},
        },
        "clumps": [
            {
                "id": 500,
                "started_at": "2025-01-01T10:00:00+00:00",
                "observations": [
                    {
                        "id": 500,
                        "user_login": "simonw",
                        "observed_at": "2025-01-01T10:00:00+00:00",
                        "latitude": 37.0,
                        "longitude": -122.0,
                        "place_ids": [11, 1],
                        "place_guess": None,
                    }
                ],
            }
        ],
    }
    output.write_text(json.dumps(seed))

    # New observation introduces place_id 12, not in cache
    new_obs = _raw_observation(600, "2025-01-01T10:30:00+00:00")
    new_obs["place_ids"] = [12, 11, 1]
    new_obs["place_guess"] = "Place"
    httpx_mock.add_response(json={"results": [new_obs]})
    httpx_mock.add_response(
        json={"results": [_place(12, "County", [1, 11])]}
    )

    main(["simonw", "--output", str(output)])

    # Two requests total: observations + places (only the missing id)
    requests = httpx_mock.get_requests()
    assert len(requests) == 2
    assert requests[1].url.path.endswith("/places/12")


def test_skipped_observations_are_counted(httpx_mock, tmp_path):
    httpx_mock.add_response(
        json={
            "results": [
                _raw_observation(1, "2025-01-01T10:00:00+00:00"),
                {**_raw_observation(2, "2025-01-01T11:00:00+00:00"), "time_observed_at": None},
            ]
        }
    )
    output = tmp_path / "out.json"

    main(["simonw", "--output", str(output)])

    data = json.loads(output.read_text())
    assert data["skipped_no_time_or_location"] == 1
    assert data["total_observations"] == 1
