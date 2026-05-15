from inaturalist_clumper.clump import build_clumps, haversine_km


def _obs(
    obs_id,
    observed_at,
    latitude,
    longitude,
    *,
    scientific_name="Felis catus",
    common_name="Domestic Cat",
    place_guess=None,
    place_ids=None,
    obscured=False,
    geoprivacy=None,
):
    return {
        "id": obs_id,
        "uri": f"https://www.inaturalist.org/observations/{obs_id}",
        "user_login": "u",
        "observed_at": observed_at,
        "latitude": latitude,
        "longitude": longitude,
        "positional_accuracy_m": 5,
        "obscured": obscured,
        "geoprivacy": geoprivacy,
        "place_guess": place_guess,
        "place_ids": list(place_ids) if place_ids is not None else [],
        "taxon": {
            "id": 1,
            "scientific_name": scientific_name,
            "common_name": common_name,
            "rank": "species",
        },
        "species_guess": common_name,
        "photos": [],
    }


def test_haversine_san_francisco_to_los_angeles():
    sf = (37.7749, -122.4194)
    la = (34.0522, -118.2437)
    km = haversine_km(*sf, *la)
    assert 555 < km < 565


def test_haversine_zero_for_identical_points():
    assert haversine_km(10.0, 20.0, 10.0, 20.0) == 0.0


def test_two_observations_within_thresholds_form_one_clump():
    a = _obs(1, "2025-01-01T10:00:00+00:00", 37.0, -122.0)
    b = _obs(2, "2025-01-01T11:30:00+00:00", 37.001, -122.001)  # ~140 m, 1.5 h
    clumps = build_clumps([a, b], max_distance_km=5.0, max_hours=3.0)
    assert len(clumps) == 1
    assert clumps[0]["observation_count"] == 2


def test_two_observations_outside_distance_form_two_clumps():
    a = _obs(1, "2025-01-01T10:00:00+00:00", 37.0, -122.0)
    b = _obs(2, "2025-01-01T11:00:00+00:00", 38.0, -122.0)  # ~111 km
    clumps = build_clumps([a, b], max_distance_km=5.0, max_hours=3.0)
    assert len(clumps) == 2


def test_two_observations_outside_time_form_two_clumps():
    a = _obs(1, "2025-01-01T10:00:00+00:00", 37.0, -122.0)
    b = _obs(2, "2025-01-01T15:00:00+00:00", 37.0, -122.0)  # 5 h apart
    clumps = build_clumps([a, b], max_distance_km=5.0, max_hours=3.0)
    assert len(clumps) == 2


def test_chain_links_via_intermediate_single_link():
    # A and C are 6 km apart (over the threshold) but B sits between them.
    # All three end up in the same clump because of single-link clustering.
    a = _obs(1, "2025-01-01T10:00:00+00:00", 37.000, -122.000)
    b = _obs(2, "2025-01-01T11:00:00+00:00", 37.027, -122.000)  # ~3.0 km from A
    c = _obs(3, "2025-01-01T12:00:00+00:00", 37.054, -122.000)  # ~3.0 km from B, ~6.0 from A
    clumps = build_clumps([a, b, c], max_distance_km=4.0, max_hours=3.0)
    assert len(clumps) == 1
    assert clumps[0]["observation_count"] == 3


def test_singleton_observation_yields_singleton_clump():
    a = _obs(1, "2025-01-01T10:00:00+00:00", 37.0, -122.0)
    clumps = build_clumps([a], max_distance_km=5.0, max_hours=3.0)
    assert len(clumps) == 1
    assert clumps[0]["observation_count"] == 1


def test_clump_metadata_started_ended_centroid_bbox_species_rollup():
    a = _obs(1, "2025-01-01T10:00:00+00:00", 37.0, -122.0, scientific_name="Felis catus", common_name="Cat")
    b = _obs(2, "2025-01-01T11:30:00+00:00", 37.002, -122.002, scientific_name="Felis catus", common_name="Cat")
    c = _obs(3, "2025-01-01T11:00:00+00:00", 37.001, -122.001, scientific_name="Canis lupus", common_name="Dog")
    clumps = build_clumps([a, b, c], max_distance_km=5.0, max_hours=3.0)
    assert len(clumps) == 1
    clump = clumps[0]
    assert clump["id"] == 1
    assert clump["started_at"] == "2025-01-01T10:00:00+00:00"
    assert clump["ended_at"] == "2025-01-01T11:30:00+00:00"
    assert clump["duration_hours"] == 1.5
    assert clump["observation_count"] == 3
    assert clump["centroid"] == [37.001, -122.001]
    assert clump["bbox"] == [[37.0, -122.002], [37.002, -122.0]]
    assert clump["span_km"] > 0
    assert clump["species"] == [
        {"scientific_name": "Felis catus", "common_name": "Cat", "count": 2},
        {"scientific_name": "Canis lupus", "common_name": "Dog", "count": 1},
    ]
    # Observations sorted by observed_at
    assert [o["id"] for o in clump["observations"]] == [1, 3, 2]


def test_clump_id_is_min_observation_id():
    a = _obs(987, "2025-01-01T10:00:00+00:00", 37.0, -122.0)
    b = _obs(123, "2025-01-01T11:00:00+00:00", 37.001, -122.001)
    c = _obs(456, "2025-01-01T12:00:00+00:00", 37.002, -122.002)
    clumps = build_clumps([a, b, c], max_distance_km=5.0, max_hours=3.0)
    assert len(clumps) == 1
    assert clumps[0]["id"] == 123


def test_clump_omits_location_when_no_place_data():
    a = _obs(1, "2025-01-01T10:00:00+00:00", 37.0, -122.0)
    b = _obs(2, "2025-01-01T11:00:00+00:00", 37.001, -122.001)
    clumps = build_clumps([a, b], max_distance_km=5.0, max_hours=3.0)
    assert "location" not in clumps[0]


def test_clump_location_uses_mode_of_place_guess():
    a = _obs(1, "2025-01-01T10:00:00+00:00", 37.0, -122.0, place_guess="Pescadero State Beach")
    b = _obs(2, "2025-01-01T10:30:00+00:00", 37.001, -122.001, place_guess="Pescadero State Beach")
    c = _obs(3, "2025-01-01T11:00:00+00:00", 37.002, -122.002, place_guess="Pescadero Marsh")
    clumps = build_clumps([a, b, c], max_distance_km=5.0, max_hours=3.0)
    assert clumps[0]["location"] == {"place_guess": "Pescadero State Beach"}


def test_clump_location_skips_obscured_for_place_guess():
    public = _obs(1, "2025-01-01T10:00:00+00:00", 37.0, -122.0, place_guess="Pescadero State Beach")
    obscured = _obs(
        2, "2025-01-01T10:30:00+00:00", 37.001, -122.001,
        place_guess="Secret Den", obscured=True,
    )
    clumps = build_clumps([public, obscured], max_distance_km=5.0, max_hours=3.0)
    assert clumps[0]["location"]["place_guess"] == "Pescadero State Beach"


def test_clump_location_skips_geoprivacy_for_place_guess():
    public = _obs(1, "2025-01-01T10:00:00+00:00", 37.0, -122.0, place_guess="Pescadero State Beach")
    private = _obs(
        2, "2025-01-01T10:30:00+00:00", 37.001, -122.001,
        place_guess="Secret Den", geoprivacy="obscured",
    )
    clumps = build_clumps([public, private], max_distance_km=5.0, max_hours=3.0)
    assert clumps[0]["location"]["place_guess"] == "Pescadero State Beach"


def test_clump_location_place_guess_none_when_all_eligible_observations_lack_it():
    a = _obs(1, "2025-01-01T10:00:00+00:00", 37.0, -122.0, place_guess=None, place_ids=[12])
    b = _obs(2, "2025-01-01T11:00:00+00:00", 37.001, -122.001, place_guess=None, place_ids=[12])
    places = {12: {"name": "X", "display_name": "X", "ancestor_ids": []}}
    clumps = build_clumps([a, b], max_distance_km=5.0, max_hours=3.0, places_lookup=places)
    assert clumps[0]["location"]["place_guess"] is None
    assert clumps[0]["location"]["place_id"] == 12


def test_clump_location_picks_most_specific_shared_place():
    places = {
        97394: {
            "name": "Pescadero State Beach",
            "display_name": "Pescadero State Beach, San Mateo County, California, US",
            "admin_level": None,
            "place_type": "Open Space",
            "ancestor_ids": [1, 11, 12],
        },
        12: {"name": "San Mateo County", "display_name": "San Mateo County, US, CA", "admin_level": 20, "ancestor_ids": [1, 11]},
        11: {"name": "California", "display_name": "California, US", "admin_level": 10, "ancestor_ids": [1]},
        1: {"name": "United States", "display_name": "United States", "admin_level": 0, "ancestor_ids": []},
    }
    a = _obs(1, "2025-01-01T10:00:00+00:00", 37.0, -122.0, place_ids=[97394, 12, 11, 1])
    b = _obs(2, "2025-01-01T11:00:00+00:00", 37.001, -122.001, place_ids=[97394, 12, 11, 1])
    clumps = build_clumps([a, b], max_distance_km=5.0, max_hours=3.0, places_lookup=places)
    location = clumps[0]["location"]
    assert location["place_id"] == 97394
    assert location["display_name"] == "Pescadero State Beach, San Mateo County, California, US"
    assert location["breadcrumb"] == [97394, 12, 11, 1]


def test_clump_location_intersects_place_ids_across_observations():
    places = {
        97394: {"name": "Park", "display_name": "Park, County, State, US", "ancestor_ids": [1, 11, 12]},
        12: {"name": "County", "display_name": "County, US", "ancestor_ids": [1, 11]},
        11: {"name": "State", "display_name": "State, US", "ancestor_ids": [1]},
        1: {"name": "US", "display_name": "US", "ancestor_ids": []},
    }
    # A is in the park, B drifted just outside it — both still share county/state/country
    a = _obs(1, "2025-01-01T10:00:00+00:00", 37.0, -122.0, place_ids=[97394, 12, 11, 1])
    b = _obs(2, "2025-01-01T11:00:00+00:00", 37.001, -122.001, place_ids=[12, 11, 1])
    clumps = build_clumps([a, b], max_distance_km=5.0, max_hours=3.0, places_lookup=places)
    location = clumps[0]["location"]
    assert location["place_id"] == 12
    assert location["display_name"] == "County, US"
    assert location["breadcrumb"] == [12, 11, 1]


def test_clump_location_place_id_none_when_no_shared_place():
    places = {
        12: {"name": "San Mateo County", "display_name": "San Mateo County, US, CA", "ancestor_ids": [1, 11]},
        13: {"name": "Santa Clara County", "display_name": "Santa Clara County, US, CA", "ancestor_ids": [1, 11]},
        11: {"name": "California", "display_name": "California, US", "ancestor_ids": [1]},
        1: {"name": "US", "display_name": "US", "ancestor_ids": []},
    }
    a = _obs(1, "2025-01-01T10:00:00+00:00", 37.0, -122.0, place_ids=[12], place_guess="Foo")
    b = _obs(2, "2025-01-01T11:00:00+00:00", 37.001, -122.001, place_ids=[13], place_guess="Foo")
    clumps = build_clumps([a, b], max_distance_km=5.0, max_hours=3.0, places_lookup=places)
    location = clumps[0]["location"]
    assert location["place_guess"] == "Foo"
    assert location["place_id"] is None
    assert location["display_name"] is None
    assert location["breadcrumb"] is None


def test_clump_location_breadcrumb_includes_only_chain_to_root():
    # When most-specific is an ancestor, its breadcrumb is just its own chain.
    places = {
        11: {"name": "California", "display_name": "California, US", "ancestor_ids": [1]},
        1: {"name": "US", "display_name": "US", "ancestor_ids": []},
    }
    a = _obs(1, "2025-01-01T10:00:00+00:00", 37.0, -122.0, place_ids=[11, 1])
    b = _obs(2, "2025-01-01T11:00:00+00:00", 37.001, -122.001, place_ids=[11, 1])
    clumps = build_clumps([a, b], max_distance_km=5.0, max_hours=3.0, places_lookup=places)
    assert clumps[0]["location"]["breadcrumb"] == [11, 1]


def test_clumps_sorted_by_started_at():
    later = _obs(1, "2025-06-01T10:00:00+00:00", 37.0, -122.0)
    earlier = _obs(2, "2025-01-01T10:00:00+00:00", 38.0, -123.0)
    clumps = build_clumps([later, earlier], max_distance_km=5.0, max_hours=3.0)
    assert [c["started_at"] for c in clumps] == [
        "2025-01-01T10:00:00+00:00",
        "2025-06-01T10:00:00+00:00",
    ]
    assert clumps[0]["id"] == 2
    assert clumps[1]["id"] == 1
