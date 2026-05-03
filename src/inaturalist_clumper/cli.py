"""Command-line entry point for the iNaturalist clumper."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .api import fetch_user_observations
from .clump import build_clumps
from .normalize import normalize
from .store import (
    extract_observations,
    load_existing,
    merge_observations,
    write_output,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inaturalist-clumper",
        description="Group iNaturalist sightings into clumps by space and time.",
    )
    parser.add_argument(
        "logins",
        nargs="+",
        help="iNaturalist user logins to fetch (one or more).",
    )
    parser.add_argument(
        "--output",
        default="clumps.json",
        help="Output JSON path (default: clumps.json). If it exists, used as the basis for an incremental run.",
    )
    parser.add_argument(
        "--distance-km",
        type=float,
        default=5.0,
        help="Spatial threshold in km for linking observations into the same clump (default: 5).",
    )
    parser.add_argument(
        "--hours",
        type=float,
        default=3.0,
        help="Temporal threshold in hours for linking observations into the same clump (default: 3).",
    )
    parser.add_argument(
        "--full-refresh",
        action="store_true",
        help="Ignore any existing observations in the output file and re-fetch from scratch.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _build_parser().parse_args(argv)
    output_path = Path(args.output)

    existing_observations: list[dict] = []
    updated_since: str | None = None
    if not args.full_refresh:
        state = load_existing(output_path)
        if state is not None:
            existing_observations = extract_observations(state)
            updated_since = state.get("generated_at")

    fresh: list[dict] = []
    skipped = 0
    for login in args.logins:
        existing_count = sum(1 for o in existing_observations if o.get("user_login") == login)
        raw = fetch_user_observations(login, updated_since=updated_since)
        print(
            f"Fetched {len(raw)} observations for {login} (existing: {existing_count})",
            file=sys.stderr,
        )
        for obs in raw:
            normalized = normalize(obs, user_login=login)
            if normalized is None:
                skipped += 1
            else:
                fresh.append(normalized)

    if skipped:
        print(
            f"Skipped {skipped} observations missing time or location",
            file=sys.stderr,
        )

    all_observations = merge_observations(existing_observations, fresh)
    clumps = build_clumps(
        all_observations,
        max_distance_km=args.distance_km,
        max_hours=args.hours,
    )

    write_output(
        output_path,
        users=list(args.logins),
        params={"max_distance_km": args.distance_km, "max_hours": args.hours},
        total_observations=len(all_observations),
        skipped_no_time_or_location=skipped,
        clumps=clumps,
    )
    print(
        f"Wrote {len(clumps)} clumps spanning {len(all_observations)} observations to {output_path}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
