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


def test_second_run_only_fetches_above_existing_max_id(httpx_mock, tmp_path):
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
    assert request.url.params["id_above"] == "500"
    assert request.url.params["user_login"] == "simonw"

    # Existing observation should still be in the output
    data = json.loads(output.read_text())
    assert data["total_observations"] == 1
    assert data["clumps"][0]["observations"][0]["id"] == 500


def test_full_refresh_ignores_existing_max_id(httpx_mock, tmp_path):
    output = tmp_path / "out.json"
    output.write_text(
        json.dumps(
            {
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
                ]
            }
        )
    )
    httpx_mock.add_response(json={"results": []})

    main(["simonw", "--output", str(output), "--full-refresh"])

    request = httpx_mock.get_requests()[0]
    assert request.url.params["id_above"] == "0"
    # Existing observation should be discarded
    data = json.loads(output.read_text())
    assert data["total_observations"] == 0


def test_multiple_users_each_get_own_id_above(httpx_mock, tmp_path):
    output = tmp_path / "out.json"
    seed = {
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
        ]
    }
    output.write_text(json.dumps(seed))
    httpx_mock.add_response(json={"results": []})  # simon583
    httpx_mock.add_response(json={"results": []})  # simonw

    main(["simon583", "simonw", "--output", str(output)])

    requests = httpx_mock.get_requests()
    by_login = {
        r.url.params["user_login"]: r.url.params["id_above"] for r in requests
    }
    assert by_login == {"simon583": "10", "simonw": "500"}


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
