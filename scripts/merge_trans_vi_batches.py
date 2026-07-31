#!/usr/bin/env python3
"""Safely merge validated translation batches into a JSONL seed."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.validate_trans_vi_batches import (
    normalize_legacy_seed_record,
    read_records,
    validate_batch,
    validate_seed,
)


def merge_batches(batch_paths, seed_path: Path, target_ids: set[int], output_path: Path) -> int:
    """Merge target batch records, rejecting invalid or conflicting duplicates."""
    batches = {}
    for batch_path in batch_paths:
        errors = validate_batch(batch_path, target_ids)
        if errors:
            raise ValueError(f"invalid batch {batch_path}: {'; '.join(errors)}")
        for _, record in read_records(batch_path):
            sense_id = record["sense_id"]
            existing = batches.get(sense_id)
            if existing is not None and existing != record:
                raise ValueError(f"conflicting sense_id {sense_id}")
            batches[sense_id] = record

    # Target rows are replaced by validated batches, so only their retained schema
    # needs checking before the strict validation of the merged output.
    seed_errors = validate_seed(seed_path, set(), require_descriptions=False)
    if seed_errors:
        raise ValueError(f"invalid seed {seed_path}: {'; '.join(seed_errors)}")
    merged = {}
    for _, record in read_records(seed_path):
        record = normalize_legacy_seed_record(record)
        sense_id = record.get("sense_id")
        if sense_id in merged:
            raise ValueError(f"duplicate seed sense_id {sense_id}")
        merged[sense_id] = record
    merged.update(batches)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temporary_path.write_text(
        "".join(json.dumps(merged[sense_id], ensure_ascii=False, separators=(",", ":")) + "\n" for sense_id in sorted(merged)),
        encoding="utf-8",
    )
    merged_errors = validate_seed(temporary_path, target_ids)
    if merged_errors:
        temporary_path.unlink()
        raise ValueError(f"invalid merged seed: {'; '.join(merged_errors)}")
    temporary_path.replace(output_path)
    return len(batches)
