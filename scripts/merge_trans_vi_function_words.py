#!/usr/bin/env python3
"""Merge one complete, validated rich function-word supplement batch."""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

try:
    from scripts.batch_trans_vi_luna_function_words import RICH_FIELDS, validate_rich_row
    from scripts.build_core_en import load_id_registry
except ModuleNotFoundError:  # direct script execution
    from batch_trans_vi_luna_function_words import RICH_FIELDS, validate_rich_row
    from build_core_en import load_id_registry


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _supplement_ids(registry_path: Path) -> set[int]:
    return {
        sense_id for source_key, sense_id in load_id_registry(registry_path).items()
        if source_key.startswith("supplement:function:")
    }


def merge_function_words(
    data_path: Path,
    rows: Path | Iterable[dict[str, Any]],
    registry_path: Path = Path("packs/en/core/sense-ids.tsv"),
) -> int:
    """Replace supplement rows atomically, requiring exact complete coverage."""
    supplement_ids = _supplement_ids(registry_path)
    raw_rows = _read_jsonl(rows) if isinstance(rows, Path) else list(rows)
    accepted: dict[int, dict[str, Any]] = {}
    for row in raw_rows:
        if not isinstance(row, dict) or set(row) != RICH_FIELDS:
            raise ValueError("incomplete rich row")
        try:
            sense_id = int(row["sense_id"])
        except (TypeError, ValueError) as error:
            raise ValueError("incomplete rich row") from error
        if sense_id not in supplement_ids:
            raise ValueError(f"unknown supplement sense_id: {sense_id}")
        if sense_id in accepted:
            raise ValueError(f"duplicate supplement sense_id: {sense_id}")
        error = validate_rich_row(row)
        if error:
            raise ValueError(f"incomplete rich row for {sense_id}: {error}")
        accepted[sense_id] = row

    missing = supplement_ids - set(accepted)
    if missing:
        raise ValueError(f"missing supplement sense_id: {min(missing)}")

    existing: dict[int, dict[str, Any]] = {}
    for row in _read_jsonl(data_path):
        sense_id = int(row["sense_id"])
        if sense_id in existing:
            raise ValueError(f"duplicate data sense_id: {sense_id}")
        existing[sense_id] = row
    existing.update(accepted)
    payload = "".join(
        json.dumps(existing[sense_id], ensure_ascii=False, separators=(",", ":")) + "\n"
        for sense_id in sorted(existing)
    )
    temporary = data_path.with_suffix(data_path.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(data_path)
    return len(accepted)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("packs/en/trans-vi/data.jsonl"))
    parser.add_argument("--registry", type=Path, default=Path("packs/en/core/sense-ids.tsv"))
    parser.add_argument("--batch", type=Path, required=True)
    args = parser.parse_args()
    print(merge_function_words(args.data, args.batch, args.registry))


if __name__ == "__main__":
    main()
