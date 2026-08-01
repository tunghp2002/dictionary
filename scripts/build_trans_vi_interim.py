#!/usr/bin/env python3
"""Build the reversible interim translation set from approved clean-AI shards."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

try:
    from scripts.validate_trans_vi_batches import validate_batch, validate_seed
except ModuleNotFoundError:
    from validate_trans_vi_batches import validate_batch, validate_seed


# Exactly the 4,675 records approved before the user requested the interim merge.
SPECS = (
    ("shard-001.jsonl", 0, 500),
    ("shard-002.jsonl", 500, 1000),
    ("shard-003.jsonl", 1000, 1500),
    ("shard-004.jsonl", 1500, 2000),
    ("shard-040.jsonl", 19500, 20000),
    ("shard-041.jsonl", 20000, 20500),
    ("shard-042.jsonl", 20500, 21000),
    ("shard-043.jsonl", 21000, 21500),
    ("shard-044.jsonl", 21500, 22000),
    ("shard-045.jsonl", 22000, 22100),
    ("shard-046.jsonl", 22500, 22575),
)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_interim(
    queue_path: Path = Path("packs/en/trans-vi/review/clean-queue.jsonl"),
    shard_dir: Path = Path("packs/en/trans-vi/review/ai-clean-v2"),
    data_path: Path = Path("packs/en/trans-vi/data.jsonl"),
    seed_path: Path = Path("packs/en/trans-vi/seed.jsonl"),
    meta_path: Path = Path("packs/en/trans-vi/meta.json"),
) -> int:
    queue = read_jsonl(queue_path)
    records: dict[int, dict] = {}
    for filename, start, end in SPECS:
        expected_ids = {int(row["sense_id"]) for row in queue[start:end]}
        selected = read_jsonl(shard_dir / filename)[: end - start]
        if len(selected) != end - start:
            raise ValueError(f"{filename}: expected {end - start} records, got {len(selected)}")
        selected_ids = [int(row["sense_id"]) for row in selected]
        if selected_ids != [int(row["sense_id"]) for row in queue[start:end]]:
            raise ValueError(f"{filename}: IDs do not match clean queue slice {start}:{end}")
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".jsonl", delete=False) as handle:
            temp_path = Path(handle.name)
            handle.write("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in selected))
        try:
            errors = validate_batch(temp_path, expected_ids)
        finally:
            temp_path.unlink(missing_ok=True)
        if errors:
            raise ValueError(f"{filename}: {'; '.join(errors[:5])}")
        for row in selected:
            sense_id = int(row["sense_id"])
            if sense_id in records:
                raise ValueError(f"duplicate sense_id {sense_id}")
            records[sense_id] = row

    if len(records) != 4675:
        raise ValueError(f"expected 4675 approved records, got {len(records)}")

    data_path.parent.mkdir(parents=True, exist_ok=True)
    ordered = [records[sense_id] for sense_id in sorted(records)]
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        data_tmp = temp_dir_path / "data.jsonl"
        data_tmp.write_text(
            "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in ordered),
            encoding="utf-8",
        )
        errors = validate_seed(data_tmp, set(records), require_descriptions=True)
        if errors:
            raise ValueError(f"interim output: {'; '.join(errors[:5])}")
        seed_tmp = temp_dir_path / "seed.jsonl"
        seed_tmp.write_text(data_tmp.read_text(encoding="utf-8"), encoding="utf-8")
        digest = hashlib.sha256(data_tmp.read_bytes()).hexdigest()
        meta = {
            "schema_version": 4,
            "key_path": "sense_id",
            "source_language": "en",
            "target_language": "vi",
            "source": "clean-ai-interim",
            "interim": True,
            "records": len(ordered),
            "filled_records": len(ordered),
            "placeholder_records": 0,
            "core_senses": len(ordered),
            "coverage": 1.0,
            "fields": ["sense_id", "meaning", "description", "examples", "collocations"],
            "schema": "packs/en/trans-vi/schema.json",
            "provenance": "AI-generated from clean OEWN word/pos/gloss queue; non-approved records removed for interim use.",
            "output": {"path": data_path.as_posix(), "sha256": digest, "bytes": data_tmp.stat().st_size},
        }
        meta_tmp = temp_dir_path / "meta.json"
        meta_tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        data_path_tmp = data_path.with_suffix(data_path.suffix + ".tmp")
        seed_path_tmp = seed_path.with_suffix(seed_path.suffix + ".tmp")
        meta_path_tmp = meta_path.with_suffix(meta_path.suffix + ".tmp")
        data_path_tmp.write_bytes(data_tmp.read_bytes())
        seed_path_tmp.write_bytes(seed_tmp.read_bytes())
        meta_path_tmp.write_bytes(meta_tmp.read_bytes())
        data_path_tmp.replace(data_path)
        seed_path_tmp.replace(seed_path)
        meta_path_tmp.replace(meta_path)
    return len(ordered)


if __name__ == "__main__":
    print(build_interim())
