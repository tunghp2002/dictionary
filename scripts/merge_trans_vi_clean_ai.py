#!/usr/bin/env python3
"""Merge a complete clean AI translation set without carrying target seed data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from scripts.validate_trans_vi_batches import (
        normalize_legacy_seed_record,
        read_records,
        validate_batch,
        validate_seed,
    )
except ModuleNotFoundError:
    from validate_trans_vi_batches import (
        normalize_legacy_seed_record,
        read_records,
        validate_batch,
        validate_seed,
    )


def merge_clean_ai_batches(
    batch_paths: list[Path],
    seed_path: Path,
    target_ids: set[int],
    output_path: Path,
) -> int:
    """Replace every target record entirely with its validated AI record.

    Unlike ``merge_trans_vi_batches``, this intentionally does not preserve old
    examples/collocations (or any other target fields).  The clean rewrite must
    be independent of the previous translation output.
    """
    if not target_ids:
        raise ValueError("target_ids must not be empty")

    ai_records: dict[int, dict] = {}
    for batch_path in batch_paths:
        errors = validate_batch(batch_path, target_ids)
        if errors:
            raise ValueError(f"invalid batch {batch_path}: {'; '.join(errors)}")
        for _, record in read_records(batch_path):
            sense_id = record["sense_id"]
            previous = ai_records.get(sense_id)
            if previous is not None and previous != record:
                raise ValueError(f"conflicting sense_id {sense_id}")
            ai_records[sense_id] = record

    missing = target_ids - set(ai_records)
    extra = set(ai_records) - target_ids
    if missing:
        raise ValueError(f"missing AI target sense_ids: {len(missing)}")
    if extra:
        raise ValueError(f"unexpected AI sense_ids: {sorted(extra)[:5]}")

    seed_errors = validate_seed(seed_path, set(), require_descriptions=False)
    if seed_errors:
        raise ValueError(f"invalid seed {seed_path}: {'; '.join(seed_errors)}")

    merged: dict[int, dict] = {}
    for _, record in read_records(seed_path):
        record = normalize_legacy_seed_record(record)
        sense_id = record["sense_id"]
        if sense_id in merged:
            raise ValueError(f"duplicate seed sense_id {sense_id}")
        if sense_id not in target_ids:
            merged[sense_id] = record
    merged.update(ai_records)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.write_text(
        "".join(
            json.dumps(merged[sense_id], ensure_ascii=False, separators=(",", ":")) + "\n"
            for sense_id in sorted(merged)
        ),
        encoding="utf-8",
    )
    merged_errors = validate_seed(temporary_path, target_ids, require_descriptions=True)
    if merged_errors:
        temporary_path.unlink()
        raise ValueError(f"invalid merged clean seed: {'; '.join(merged_errors)}")
    temporary_path.replace(output_path)
    return len(ai_records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", action="append", type=Path, required=True)
    parser.add_argument("--seed", type=Path, default=Path("packs/en/trans-vi/seed.jsonl"))
    parser.add_argument("--target-manifest", type=Path, default=Path("packs/en/trans-vi/target-manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("packs/en/trans-vi/seed.jsonl"))
    args = parser.parse_args()
    manifest = json.loads(args.target_manifest.read_text(encoding="utf-8"))
    target_ids = {int(value) for value in manifest["target_sense_ids"]}
    count = merge_clean_ai_batches(args.batch, args.seed, target_ids, args.output)
    print(count)


if __name__ == "__main__":
    main()
