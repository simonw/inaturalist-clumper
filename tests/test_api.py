from inaturalist_clumper.api import (
    BASE_URL,
    USER_AGENT,
    fetch_user_observations,
)


def test_fetch_paginates_with_id_above_until_short_page(httpx_mock):
    page1 = [{"id": i} for i in range(1, 201)]
    page2 = [{"id": i} for i in range(201, 218)]
    httpx_mock.add_response(json={"results": page1})
    httpx_mock.add_response(json={"results": page2})

    results = fetch_user_observations("simonw", sleep_seconds=0)

    assert [r["id"] for r in results] == list(range(1, 218))
    requests = httpx_mock.get_requests()
    assert len(requests) == 2
    assert requests[0].url.params["id_above"] == "0"
    assert requests[0].url.params["user_login"] == "simonw"
    assert requests[0].url.params["per_page"] == "200"
    assert requests[0].url.params["order_by"] == "id"
    assert requests[0].url.params["order"] == "asc"
    assert requests[1].url.params["id_above"] == "200"


def test_fetch_stops_when_first_page_is_short(httpx_mock):
    httpx_mock.add_response(json={"results": [{"id": 1}, {"id": 2}]})
    results = fetch_user_observations("simon583", sleep_seconds=0)
    assert len(results) == 2
    assert len(httpx_mock.get_requests()) == 1


def test_fetch_returns_empty_list_when_no_results(httpx_mock):
    httpx_mock.add_response(json={"results": []})
    assert fetch_user_observations("nobody", sleep_seconds=0) == []


def test_fetch_includes_user_agent_header(httpx_mock):
    httpx_mock.add_response(json={"results": []})
    fetch_user_observations("simonw", sleep_seconds=0)
    request = httpx_mock.get_requests()[0]
    assert request.headers["user-agent"] == USER_AGENT


def test_fetch_starts_from_id_above_when_provided(httpx_mock):
    httpx_mock.add_response(json={"results": []})
    fetch_user_observations("simonw", id_above=12345, sleep_seconds=0)
    request = httpx_mock.get_requests()[0]
    assert request.url.params["id_above"] == "12345"


def test_fetch_targets_correct_endpoint(httpx_mock):
    httpx_mock.add_response(json={"results": []})
    fetch_user_observations("simonw", sleep_seconds=0)
    url = httpx_mock.get_requests()[0].url
    assert str(url).startswith(BASE_URL)
