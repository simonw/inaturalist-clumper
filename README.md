# inaturalist-clumper

Group iNaturalist sightings into clumps.

Given one or more iNaturalist user logins, this CLI fetches every public
observation those users have recorded and groups sightings that happened
**within ~5 km and ~3 hours of each other** into "clumps" — useful for
reconstructing a single hike, birding session, or tide-pool visit as one
record.

The output JSON file records, for every clump:

- start/end timestamps, duration, centroid, bounding box, span
- a species roll-up
- per-observation: timestamp, latitude/longitude, identified taxon, and
  photo URLs (thumbnail / large / original)

## Install

Requires [uv](https://docs.astral.sh/uv/).

```
uv sync
```

## Usage

```
uv run inaturalist-clumper simon583 simonw --output clumps.json
```

Options:

| Flag              | Default        | Description                                                                |
| ----------------- | -------------- | -------------------------------------------------------------------------- |
| `LOGIN ...`       | _required_     | One or more iNaturalist user logins to fetch.                              |
| `--output`        | `clumps.json`  | Output JSON path. Used as the basis for incremental runs if it exists.     |
| `--distance-km`   | `5.0`          | Spatial threshold for linking two observations into the same clump.        |
| `--hours`         | `3.0`          | Temporal threshold for linking two observations into the same clump.       |
| `--full-refresh`  | _off_          | Ignore any existing observations in the output file and re-fetch fully.    |

### Incremental runs

A second invocation against the same `--output` file reads the existing
data and asks the iNaturalist API for any observations that have been
created or edited since the previous run's `generated_at` timestamp
(using the `updated_since` parameter). Edited records overwrite the
cached copy on merge, so corrected taxa, new photos, or fixed coordinates
flow back in. The full set is then re-clumped and the file rewritten —
so a new sighting that bridges two previous clumps will merge them.

Use `--full-refresh` to ignore the existing file and start over.

## Development

```
uv run pytest
```

Tests use [`pytest-httpx`](https://pypi.org/project/pytest-httpx/) to mock
the iNaturalist API — no real network calls are made.
