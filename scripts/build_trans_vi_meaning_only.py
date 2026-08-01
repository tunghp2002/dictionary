#!/usr/bin/env python3
"""Rebuild the full sense table while retaining only short Vietnamese meanings."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

try:
    from scripts.build_core_en import load_id_registry
except ModuleNotFoundError:
    from build_core_en import load_id_registry


def read_jsonl(path: Path) -> dict[int, dict]:
    return {
        int(row["sense_id"]): row
        for row in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    }


def build_meaning_only(
    registry_path: Path,
    source_path: Path,
    data_path: Path,
    seed_path: Path,
    meta_path: Path,
) -> dict:
    ids = sorted(load_id_registry(registry_path).values())
    source = read_jsonl(source_path)
    records = [
        {
            "sense_id": sense_id,
            "meaning": str(source.get(sense_id, {}).get("meaning", "")).strip(),
            "description": "",
            "examples": [],
            "collocations": [],
        }
        for sense_id in ids
    ]
    data_path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in records)
    data_path.write_text(payload, encoding="utf-8")
    seed_path.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(data_path.read_bytes()).hexdigest()
    filled = sum(bool(row["meaning"]) for row in records)
    meta = {
        "schema_version": 4,
        "key_path": "sense_id",
        "source_language": "en",
        "target_language": "vi",
        "source": "clean-ai-meaning-only",
        "records": len(records),
        "filled_records": filled,
        "placeholder_records": len(records) - filled,
        "core_senses": len(records),
        "coverage": filled / len(records) if records else 0,
        "fields": ["sense_id", "meaning", "description", "examples", "collocations"],
        "schema": "packs/en/trans-vi/schema.json",
        "output": {"path": data_path.as_posix(), "sha256": digest, "bytes": data_path.stat().st_size},
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=Path("packs/en/core/sense-ids.tsv"))
    parser.add_argument("--source", type=Path, default=Path("packs/en/trans-vi/seed.jsonl"))
    parser.add_argument("--data", type=Path, default=Path("packs/en/trans-vi/data.jsonl"))
    parser.add_argument("--seed", type=Path, default=Path("packs/en/trans-vi/seed.jsonl"))
    parser.add_argument("--meta", type=Path, default=Path("packs/en/trans-vi/meta.json"))
    args = parser.parse_args()
    print(json.dumps(build_meaning_only(args.registry, args.source, args.data, args.seed, args.meta), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
