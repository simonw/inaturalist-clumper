from inaturalist_clumper.normalize import normalize


def _raw_observation(**overrides):
    base = {
        "id": 265422821,
        "uri": "https://www.inaturalist.org/observations/265422821",
        "time_observed_at": "2025-03-15T08:47:39-07:00",
        "geojson": {"type": "Point", "coordinates": [-122.4948015608, 37.495576544]},
        "positional_accuracy": 2,
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
                "id": 308290899,
                "license_code": "cc-by-nc",
                "url": "https://inaturalist-open-data.s3.amazonaws.com/photos/308290899/square.jpg",
                "attribution": "(c) Simon Willison, some rights reserved (CC BY-NC)",
                "original_dimensions": {"width": 2048, "height": 1365},
            }
        ],
    }
    base.update(overrides)
    return base


def test_normalize_extracts_core_fields():
    record = normalize(_raw_observation(), user_login="simonw")
    assert record == {
        "id": 265422821,
        "uri": "https://www.inaturalist.org/observations/265422821",
        "user_login": "simonw",
        "observed_at": "2025-03-15T08:47:39-07:00",
        "latitude": 37.495576544,
        "longitude": -122.4948015608,
        "positional_accuracy_m": 2,
        "obscured": False,
        "geoprivacy": None,
        "place_guess": None,
        "place_ids": [],
        "taxon": {
            "id": 4940,
            "scientific_name": "Egretta thula",
            "common_name": "Snowy Egret",
            "rank": "species",
        },
        "species_guess": "Snowy Egret",
        "photos": [
            {
                "id": 308290899,
                "thumbnail_url": "https://inaturalist-open-data.s3.amazonaws.com/photos/308290899/medium.jpg",
                "large_url": "https://inaturalist-open-data.s3.amazonaws.com/photos/308290899/large.jpg",
                "original_url": "https://inaturalist-open-data.s3.amazonaws.com/photos/308290899/original.jpg",
                "original_dimensions": {"width": 2048, "height": 1365},
                "attribution": "(c) Simon Willison, some rights reserved (CC BY-NC)",
                "license_code": "cc-by-nc",
            }
        ],
    }


def test_photo_urls_swap_square_for_medium_large_original_on_static_host():
    raw = _raw_observation(
        photos=[
            {
                "id": 107527504,
                "license_code": None,
                "url": "https://static.inaturalist.org/photos/107527504/square.jpeg",
                "attribution": "x",
            }
        ]
    )
    record = normalize(raw, user_login="simonw")
    photo = record["photos"][0]
    assert photo["thumbnail_url"] == "https://static.inaturalist.org/photos/107527504/medium.jpeg"
    assert photo["large_url"] == "https://static.inaturalist.org/photos/107527504/large.jpeg"
    assert photo["original_url"] == "https://static.inaturalist.org/photos/107527504/original.jpeg"


def test_photo_original_dimensions_preserved():
    raw = _raw_observation(
        photos=[
            {
                "id": 1,
                "url": "https://inaturalist-open-data.s3.amazonaws.com/photos/1/square.jpg",
                "original_dimensions": {"width": 1600, "height": 1200},
            }
        ]
    )
    record = normalize(raw, user_login="simonw")
    assert record["photos"][0]["original_dimensions"] == {"width": 1600, "height": 1200}


def test_photo_original_dimensions_defaults_to_none_when_missing():
    raw = _raw_observation(
        photos=[
            {
                "id": 1,
                "url": "https://inaturalist-open-data.s3.amazonaws.com/photos/1/square.jpg",
            }
        ]
    )
    record = normalize(raw, user_login="simonw")
    assert record["photos"][0]["original_dimensions"] is None


def test_normalize_skips_when_time_missing():
    raw = _raw_observation(time_observed_at=None)
    assert normalize(raw, user_login="simonw") is None


def test_normalize_skips_when_geojson_missing():
    raw = _raw_observation(geojson=None)
    assert normalize(raw, user_login="simonw") is None


def test_taxon_falls_back_to_species_guess_when_taxon_null():
    raw = _raw_observation(taxon=None)
    record = normalize(raw, user_login="simonw")
    assert record["taxon"] is None
    assert record["species_guess"] == "Snowy Egret"


def test_observation_with_no_photos():
    raw = _raw_observation(photos=[])
    record = normalize(raw, user_login="simonw")
    assert record["photos"] == []


def test_normalize_passes_through_place_guess_and_place_ids():
    raw = _raw_observation(
        place_guess="Pescadero State Beach",
        place_ids=[97394, 12, 11, 1],
    )
    record = normalize(raw, user_login="simonw")
    assert record["place_guess"] == "Pescadero State Beach"
    assert record["place_ids"] == [97394, 12, 11, 1]


def test_normalize_place_ids_defaults_to_empty_list_when_missing():
    raw = _raw_observation()
    raw.pop("place_ids", None)
    record = normalize(raw, user_login="simonw")
    assert record["place_ids"] == []


def test_normalize_place_ids_treats_null_as_empty_list():
    raw = _raw_observation(place_ids=None)
    record = normalize(raw, user_login="simonw")
    assert record["place_ids"] == []
