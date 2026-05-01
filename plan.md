# Plan: iNaturalist sighting clumper

## Context

The repo is empty apart from a stub README. Goal: a small Python CLI that pulls every observation by one or more iNaturalist users from the public v1 API and groups sightings that happened **within ~5 km and ~3 hours of each other** into "clumps" — useful for reconstructing a single hike, birding session, or tide-pool visit as one record. Output goes to a JSON file recording per-observation timestamps, lat/lon, identified species, and photo URLs (high-res + thumbnails).

The tool must be **re-runnable**: a second invocation against the same output file reads existing data, fetches only observations newer than what's already recorded for each user, and rewrites the file with merged + re-clumped data.

Confirmed targets:
- `simon583` — 12 observations
- `simonw` — Simon Willison, 300 observations (the intended `simonwillison`; that handle does not exist)

## Key API findings

- Endpoint: `GET https://api.inaturalist.org/v1/observations`
- Filter by user with `user_login=<login>` (note: `simonwillison` returns HTTP 422 "Unknown user_id"; `simonw` works)
- `per_page` max 200; recommended pagination uses `order_by=id&order=asc` plus `id_above=<last_id>` (cursor-style) — perfect for both initial backfill *and* incremental fetches.
- Rate limits: 100 req/min hard, 60 req/min recommended; ≤ 24 GB media/day. We sleep 1 s between requests.
- Photo URL pattern: every photo's `url` is the `square.jpg` (75 px) variant; swap `square` for `small` (240 px), `medium` (500 px), `large` (1024 px), or `original` to get other sizes. Hosts: `inaturalist-open-data.s3.amazonaws.com` and `static.inaturalist.org` — swap works on both.
- Each observation includes `geojson.coordinates` as `[lon, lat]`, `time_observed_at` (ISO 8601 with offset), `taxon` (with `name`, `preferred_common_name`, `rank`), `photos[]`, `obscured`, `geoprivacy`, `positional_accuracy`, `uri`.

## Project setup

- `pyproject.toml` — declares the package and CLI entrypoint
  - Runtime dep: `httpx`
  - Dev deps: `pytest`, `pytest-httpx`
  - `[project.scripts]` entry: `inaturalist-clumper = "inaturalist_clumper.cli:main"`
- `src/inaturalist_clumper/` package layout:
  - `__init__.py`
  - `cli.py` — argparse + main entrypoint
  - `api.py` — httpx-based fetch loop (`fetch_user_observations`)
  - `normalize.py` — observation flattening + photo URL derivation
  - `clump.py` — haversine, union-find, clump assembly
  - `store.py` — load existing JSON, merge new observations, write JSON
- `tests/` directory (pytest)
- `README.md` — usage example

Run tests with `uv run pytest`.

## CLI interface

```
inaturalist-clumper LOGIN [LOGIN ...]
    [--output PATH]
    [--distance-km FLOAT]
    [--hours FLOAT]
    [--full-refresh]
```

| Flag | Default | Behaviour |
| --- | --- | --- |
| positional `LOGIN ...` | (required, ≥1) | iNaturalist user logins to fetch. |
| `--output` | `clumps.json` | Output JSON path. If it exists and is readable, used as the basis for an incremental run. |
| `--distance-km` | `5.0` | Spatial threshold for linking two observations into the same clump. |
| `--hours` | `3.0` | Temporal threshold for linking two observations into the same clump. |
| `--full-refresh` | off | Ignore any existing observations in the output file and re-fetch from scratch. |

A fixed `User-Agent` of `inaturalist-clumper/0.1 (+https://github.com/simonw/inaturalist-clumper)` is hard-coded in `api.py`.

Behaviour:
1. If the output file exists and `--full-refresh` not set: load it; build per-user `max_id` (the highest observation id already recorded for each requested login).
2. For each requested login, fetch with `id_above=<max_id or 0>`. Logins absent from the existing file get `id_above=0`.
3. Merge new observations with existing ones; dedupe by observation `id`.
4. **Re-clump all observations** (not just new ones) — a new sighting can bridge or extend existing clumps, and the clump thresholds may have changed between runs.
5. Write the file back.

Console output (stderr): `Fetched 17 new observations for simonw (existing: 300)`, `Skipped 2 observations missing time/location`, `Wrote 47 clumps spanning 314 observations to clumps.json`.

## Persisted JSON format

The on-disk JSON is the *single source of truth* for the next run, so it stores both the materialised clumps and the inputs that produced them:

```json
{
  "generated_at": "2026-05-01T18:42:11Z",
  "users": ["simon583", "simonw"],
  "params": {"max_distance_km": 5.0, "max_hours": 3.0},
  "total_observations": 312,
  "skipped_no_time_or_location": 0,
  "total_clumps": 47,
  "clumps": [
    {
      "id": 1,
      "started_at": "2024-08-12T07:14:00-07:00",
      "ended_at":   "2024-08-12T09:51:22-07:00",
      "duration_hours": 2.62,
      "centroid": [37.4955, -122.4948],
      "bbox": [[37.491, -122.501], [37.499, -122.488]],
      "span_km": 1.04,
      "observation_count": 6,
      "species": [
        {"scientific_name": "Egretta thula", "common_name": "Snowy Egret", "count": 2},
        ...
      ],
      "observations": [ /* normalized records, sorted by observed_at */ ]
    }
  ]
}
```

Each `observations[]` entry has the shape:

```json
{
  "id": 265422821,
  "uri": "https://www.inaturalist.org/observations/265422821",
  "user_login": "simonw",
  "observed_at": "2025-03-15T08:47:39-07:00",
  "latitude": 37.495576544,
  "longitude": -122.4948015608,
  "positional_accuracy_m": 2,
  "obscured": false,
  "geoprivacy": null,
  "taxon": {
    "id": 4940,
    "scientific_name": "Egretta thula",
    "common_name": "Snowy Egret",
    "rank": "species"
  },
  "species_guess": "Snowy Egret",
  "photos": [
    {
      "id": 308290899,
      "thumbnail_url": "https://.../308290899/medium.jpg",
      "large_url":     "https://.../308290899/large.jpg",
      "original_url":  "https://.../308290899/original.jpg",
      "attribution": "(c) Simon Willison, some rights reserved (CC BY-NC)",
      "license_code": "cc-by-nc"
    }
  ]
}
```

Reload path on incremental runs: walk every clump's `observations[]`, dedupe by `id`, recompute `max_id` per `user_login`.

## Algorithms

**Photo URL derivation** (`normalize.py`): `re.sub(r'/square\.(jpe?g|png)$', f'/{size}.\\1', url)` for `medium`, `large`, `original`. Works for both S3 and `static.inaturalist.org` hosts.

**Haversine distance** (`clump.py`): stdlib `math` only; Earth radius 6371 km; returns km.

**Clumping** (`clump.py`): single-link clustering via Union-Find. For each pair (i, j) where `j > i`: if `haversine(a, b) ≤ max_km` and `abs(t_a − t_b) ≤ max_hours`, union. n² is fine for ~thousands. Drop observations missing `observed_at` or coordinates upfront and report the count.

For each clump compute: `started_at`/`ended_at`/`duration_hours`, centroid (mean lat/lon), bbox, `span_km` (haversine across bbox diagonal), `species` rollup sorted by count desc, observations sorted by `observed_at`. Sort clumps by `started_at`.

## TDD plan (red → green per step)

Tests live in `tests/`. Use `pytest-httpx`'s `httpx_mock` fixture to stub `https://api.inaturalist.org/v1/observations` — no real network calls in tests. Run via `uv run pytest`.

Suggested order; commit after each green:

1. **`tests/test_normalize.py`**
   - `test_normalize_extracts_core_fields` — minimal observation dict → expected flat record.
   - `test_photo_urls_swap_square_for_medium_large_original` — assert all three URL variants for both S3 and static-inaturalist hosts.
   - `test_normalize_skips_when_time_or_location_missing` — returns `None` (or marker) so caller can count skips.
   - `test_taxon_falls_back_to_species_guess` — handles `taxon: null`.

2. **`tests/test_clump.py`**
   - `test_haversine_known_distance` — SF ↔ LA ≈ 559 km, tolerance.
   - `test_two_observations_within_thresholds_form_one_clump`.
   - `test_two_observations_outside_distance_form_two_clumps`.
   - `test_two_observations_outside_time_form_two_clumps`.
   - `test_chain_links_via_intermediate` — A–B linked, B–C linked, A–C not directly linked → all in one clump (single-link).
   - `test_singleton_observation_yields_singleton_clump`.
   - `test_clump_metadata_started_ended_centroid_bbox_species_rollup`.

3. **`tests/test_api.py`** (uses `httpx_mock`)
   - `test_fetch_paginates_with_id_above_until_short_page` — mock two pages: 200 results then 17, assert two calls with correct `id_above` values, returns 217 records.
   - `test_fetch_includes_user_agent_header`.
   - `test_fetch_uses_id_above_when_provided` — incremental case: starting `id_above=12345` shows up in the first request URL.
   - (Skip rate-limit/sleep tests — keep behaviour simple; sleep is a constant, monkeypatch `time.sleep` to a no-op in tests.)

4. **`tests/test_store.py`**
   - `test_load_returns_empty_state_when_file_missing`.
   - `test_load_recovers_max_id_per_user_from_existing_clumps`.
   - `test_merge_dedupes_by_observation_id` — overlapping ids prefer the freshly fetched record.
   - `test_write_then_load_roundtrips`.

5. **`tests/test_cli.py`** (uses `httpx_mock` + `tmp_path`)
   - `test_first_run_writes_clumps_json` — mock API for a single user, run `main([...])`, assert file contents structure.
   - `test_second_run_only_fetches_above_existing_max_id` — pre-seed `clumps.json`, run, assert mocked request URL contains `id_above=<expected>`.
   - `test_full_refresh_ignores_existing_file`.
   - `test_multiple_users_each_get_own_id_above`.

After tests pass, do a real-network smoke run against `simon583` (12 obs) — manually invoked, not in the test suite — and spot-check output.

## Files to create

```
pyproject.toml
src/inaturalist_clumper/__init__.py
src/inaturalist_clumper/api.py
src/inaturalist_clumper/normalize.py
src/inaturalist_clumper/clump.py
src/inaturalist_clumper/store.py
src/inaturalist_clumper/cli.py
tests/test_normalize.py
tests/test_clump.py
tests/test_api.py
tests/test_store.py
tests/test_cli.py
README.md  (update with usage)
```

## Verification

1. `uv sync` (or `uv pip install -e ".[dev]"`).
2. `uv run pytest` — all tests green.
3. Real-network smoke: `uv run inaturalist-clumper simon583 --output /tmp/simon583.json` — finishes in seconds, ≤ 12 observations, plausible clumps.
4. Spot-check: open `/tmp/simon583.json`, pick a multi-observation clump, click through `uri` links and confirm the observations were genuinely from one outing.
5. Incremental check: run the same command again immediately. Stderr should report `Fetched 0 new observations`. File mtime updates, content equivalent (modulo `generated_at`).
6. Full run: `uv run inaturalist-clumper simon583 simonw --output clumps.json` — expect ~312 observations.
7. Threshold sweep: re-run with `--distance-km 1 --hours 1` and `--distance-km 20 --hours 12`; clump count should rise then fall.
8. Confirm photo URLs resolve: `curl -I` one of the `large_url` entries returns 200.

## Out of scope

- OAuth / authenticated endpoints — everything we need is public.
- Resolving obscured coordinates — record `obscured: true` and use the public-fuzzy lat/lon iNat returns.
- Detecting *edits* to already-fetched observations (incremental refresh is new-only via `id_above`). A `--full-refresh` flag is the escape hatch.
- HTML/Markdown rendering — JSON only.
