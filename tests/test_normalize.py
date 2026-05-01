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
