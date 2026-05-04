#!/usr/bin/env python3
"""
Combine all ar*.json command descriptions from a Redis source tree into one
JSON file that drives the playground UI.

Usage:
    python build_commands_json.py [REDIS_SRC_DIR] [OUTPUT_PATH]

Defaults:
    REDIS_SRC_DIR = /tmp/redis/src/commands
    OUTPUT_PATH   = ./commands.json

The output is shaped like:

    {
        "ARSET":    { ...command spec... },
        "ARGET":    { ...command spec... },
        ...
    }
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def build(src_dir: Path) -> dict:
    combined: dict[str, dict] = {}
    paths = sorted(src_dir.glob("ar*.json"))
    if not paths:
        raise SystemExit(f"no ar*.json files found under {src_dir}")

    for path in paths:
        with path.open() as f:
            data = json.load(f)
        if len(data) != 1:
            raise SystemExit(f"{path} should have exactly one top-level key")
        name, spec = next(iter(data.items()))
        combined[name] = spec

    return combined


def main(argv: list[str]) -> int:
    src_dir = Path(argv[1]) if len(argv) > 1 else Path("/tmp/redis/src/commands")
    out_path = Path(argv[2]) if len(argv) > 2 else Path("commands.json")

    combined = build(src_dir)

    out_path.write_text(json.dumps(combined, indent=2) + "\n")
    print(f"wrote {len(combined)} commands -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
