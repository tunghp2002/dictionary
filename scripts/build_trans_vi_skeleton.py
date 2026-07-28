#!/usr/bin/env python3
"""Build the English-to-Vietnamese ID skeleton around the curated seed."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.build_core_en import file_sha256, load_id_registry, write_jsonl
except ModuleNotFoundError:  # direct `python scripts/build_trans_vi_skeleton.py`
    from build_core_en import file_sha256, load_id_registry, write_jsonl


TRANSLATION_FIELDS = {"sense_id", "meaning", "examples", "collocations"}


def load_seed(path: Path) -> dict[int, dict[str, Any]]:
    seed: dict[int, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if set(record) != TRANSLATION_FIELDS:
                raise ValueError(
                    f"Invalid translation fields: {sorted(set(record) - TRANSLATION_FIELDS)}"
                )
            sense_id = int(record["sense_id"])
            if sense_id in seed:
                raise ValueError(f"Duplicate seed sense_id: {sense_id}")
            seed[sense_id] = record
    return seed


def build(
    registry_path: Path,
    seed_path: Path,
    output_path: Path,
    metadata_path: Path,
) -> dict[str, Any]:
    registry = load_id_registry(registry_path)
    seed = load_seed(seed_path)
    core_ids = set(registry.values())
    unknown_ids = set(seed) - core_ids
    if unknown_ids:
        raise ValueError(f"Seed IDs missing from core registry: {sorted(unknown_ids)[:5]}")

    records = []
    for sense_id in sorted(core_ids):
        records.append(
            seed.get(
                sense_id,
                {
                    "sense_id": sense_id,
                    "meaning": "",
                    "examples": [],
                    "collocations": [],
                },
            )
        )
    write_jsonl(output_path, records)
    metadata = {
        "schema_version": 3,
        "key_path": "sense_id",
        "source_language": "en",
        "target_language": "vi",
        "source": "curated-seed-plus-skeleton",
        "records": len(records),
        "filled_records": len(seed),
        "placeholder_records": len(records) - len(seed),
        "core_senses": len(registry),
        "coverage": len(seed) / len(registry) if registry else 0,
        "fields": ["sense_id", "meaning", "examples", "collocations"],
        "schema": "packs/en/trans-vi/schema.json",
        "output": {
            "path": output_path.as_posix(),
            "sha256": file_sha256(output_path),
            "bytes": output_path.stat().st_size,
        },
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-registry", type=Path, default=Path("packs/en/core/sense-ids.tsv"))
    parser.add_argument("--seed", type=Path, default=Path("packs/en/trans-vi/seed.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("packs/en/trans-vi/data.jsonl"))
    parser.add_argument("--metadata-output", type=Path, default=Path("packs/en/trans-vi/meta.json"))
    args = parser.parse_args()
    print(json.dumps(build(args.core_registry, args.seed, args.output, args.metadata_output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
