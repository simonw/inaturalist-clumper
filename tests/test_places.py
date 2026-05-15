from inaturalist_clumper.places import PLACES_BASE_URL, fetch_places


def test_fetch_places_returns_normalized_records(httpx_mock):
    httpx_mock.add_response(
        json={
            "results": [
                {
                    "id": 12,
                    "name": "San Mateo County",
                    "display_name": "San Mateo County, US, CA",
                    "admin_level": 20,
                    "place_type": 9,
                    "ancestor_place_ids": [1, 11, 12],
                },
                {
                    "id": 97394,
                    "name": "Pescadero State Beach",
                    "display_name": "Pescadero State Beach, San Mateo County, California, US",
                    "admin_level": None,
                    "place_type": 100,
                    "ancestor_place_ids": [1, 11, 12, 97394],
                },
            ]
        }
    )
    result = fetch_places([12, 97394])
    assert result == {
        12: {
            "name": "San Mateo County",
            "display_name": "San Mateo County, US, CA",
            "admin_level": 20,
            "place_type": 9,
            "ancestor_ids": [1, 11],
        },
        97394: {
            "name": "Pescadero State Beach",
            "display_name": "Pescadero State Beach, San Mateo County, California, US",
            "admin_level": None,
            "place_type": 100,
            "ancestor_ids": [1, 11, 12],
        },
    }


def test_fetch_places_empty_input_makes_no_request(httpx_mock):
    assert fetch_places([]) == {}
    assert httpx_mock.get_requests() == []


def test_fetch_places_dedupes_input(httpx_mock):
    httpx_mock.add_response(json={"results": [{"id": 1, "name": "X", "display_name": "X", "ancestor_place_ids": []}]})
    fetch_places([1, 1, 1])
    request = httpx_mock.get_requests()[0]
    assert request.url.path.endswith("/places/1")


def test_fetch_places_batches_when_over_limit(httpx_mock):
    ids = list(range(1, 41))  # 40 ids, batch_size=30 → 2 requests
    httpx_mock.add_response(
        json={"results": [{"id": i, "name": str(i), "display_name": str(i), "ancestor_place_ids": []} for i in range(1, 31)]}
    )
    httpx_mock.add_response(
        json={"results": [{"id": i, "name": str(i), "display_name": str(i), "ancestor_place_ids": []} for i in range(31, 41)]}
    )
    result = fetch_places(ids, sleep_seconds=0)
    requests = httpx_mock.get_requests()
    assert len(requests) == 2
    assert len(result) == 40


def test_fetch_places_hits_correct_endpoint(httpx_mock):
    httpx_mock.add_response(json={"results": []})
    fetch_places([42])
    url = str(httpx_mock.get_requests()[0].url)
    assert url.startswith(PLACES_BASE_URL)
    assert url.endswith("/42")


def test_fetch_places_strips_self_from_ancestors(httpx_mock):
    httpx_mock.add_response(
        json={"results": [{"id": 5, "name": "X", "display_name": "X", "ancestor_place_ids": [1, 2, 5]}]}
    )
    result = fetch_places([5])
    assert result[5]["ancestor_ids"] == [1, 2]


def test_fetch_places_handles_missing_ancestor_place_ids(httpx_mock):
    httpx_mock.add_response(
        json={"results": [{"id": 5, "name": "X", "display_name": "X"}]}
    )
    result = fetch_places([5])
    assert result[5]["ancestor_ids"] == []
