#!/usr/bin/env python3
"""Rebuild canonical Vietnamese records, preserving validated rich fields."""

from __future__ import annotations

import argparse
import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any

try:
    from scripts.batch_trans_vi_luna_function_words import RICH_FIELDS, validate_rich_row
    from scripts.build_core_en import load_id_registry
    from scripts.build_en_function_words import load_function_words
except ModuleNotFoundError:  # direct script execution
    from batch_trans_vi_luna_function_words import RICH_FIELDS, validate_rich_row
    from build_core_en import load_id_registry
    from build_en_function_words import load_function_words


FIELDS = ["sense_id", "meaning", "description", "examples", "collocations"]


def _normalize_nfc(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_normalize_nfc(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_nfc(item) for key, item in value.items()}
    return value


def _read_source(path: Path, registry_ids: set[int]) -> dict[int, dict[str, Any]]:
    records: dict[int, dict[str, Any]] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = _normalize_nfc(json.loads(line))
        if not isinstance(row, dict) or set(row) != set(FIELDS):
            raise ValueError(f"source line {line_number}: expected exact canonical schema")
        sense_id = row["sense_id"]
        if not isinstance(sense_id, int) or isinstance(sense_id, bool):
            raise ValueError(f"source line {line_number}: invalid sense_id")
        if sense_id not in registry_ids:
            raise ValueError(f"source line {line_number}: unknown sense_id {sense_id}")
        if sense_id in records:
            raise ValueError(f"source line {line_number}: duplicate sense_id {sense_id}")
        if not isinstance(row["meaning"], str) or not isinstance(row["description"], str) or not isinstance(row["examples"], list) or not isinstance(row["collocations"], list):
            raise ValueError(f"source line {line_number}: invalid canonical value types")
        records[sense_id] = row
    return records


def build_canonical(
    registry_path: Path,
    source_path: Path,
    data_path: Path,
    seed_path: Path,
    meta_path: Path,
) -> dict[str, Any]:
    """Write data, seed, and metadata from one fully validated source payload."""
    registry = load_id_registry(registry_path)
    ids = set(registry.values())
    source = _read_source(source_path, ids)
    supplements = {sense_id for source_key, sense_id in registry.items() if source_key.startswith("supplement:function:")}
    expansion_manifest = registry_path.parent / "function-words-expansion.jsonl"
    expansion_ids = ({registry[row["source_key"]] for row in load_function_words(expansion_manifest)}
                     if expansion_manifest.exists() else supplements)
    missing_supplements = supplements - set(source)
    if missing_supplements:
        raise ValueError(f"missing supplement source record: {min(missing_supplements)}")

    records = []
    for sense_id in sorted(ids):
        source_row = source.get(sense_id, {})
        record = {
            "sense_id": sense_id,
            "meaning": str(source_row.get("meaning", "")).strip(),
            "description": str(source_row.get("description", "")).strip(),
            "examples": source_row.get("examples", []),
            "collocations": source_row.get("collocations", []),
        }
        if sense_id in supplements:
            error = validate_rich_row(source_row) if sense_id in expansion_ids else validate_rich_row({**source_row, "meaning": "một"})
            if error:
                raise ValueError(f"invalid supplement source record {sense_id}: {error}")
            record.update({field: source_row[field] for field in FIELDS if field != "sense_id"})
        records.append(record)

    payload = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in records)
    data_path.parent.mkdir(parents=True, exist_ok=True)
    seed_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(payload, encoding="utf-8")
    seed_path.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(data_path.read_bytes()).hexdigest()
    filled = sum(bool(row["meaning"]) for row in records)
    metadata = {
        "schema_version": 4,
        "key_path": "sense_id",
        "source_language": "en",
        "target_language": "vi",
        "license": "CC-BY-SA-4.0",
        "attribution": "DATA_LICENSES.md",
        "source": "canonical-meaning-plus-oewn-description-and-rich-fields",
        "records": len(records),
        "filled_records": filled,
        "placeholder_records": len(records) - filled,
        "core_senses": len(records),
        "coverage": filled / len(records) if records else 0,
        "fields": FIELDS,
        "schema": "packs/en/trans-vi/schema.json",
        "output": {"path": data_path.as_posix(), "sha256": digest, "bytes": data_path.stat().st_size},
    }
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=Path("packs/en/core/sense-ids.tsv"))
    parser.add_argument("--source", type=Path, default=Path("packs/en/trans-vi/data.jsonl"))
    parser.add_argument("--data", type=Path, default=Path("packs/en/trans-vi/data.jsonl"))
    parser.add_argument("--seed", type=Path, default=Path("packs/en/trans-vi/seed.jsonl"))
    parser.add_argument("--meta", type=Path, default=Path("packs/en/trans-vi/meta.json"))
    args = parser.parse_args()
    print(json.dumps(build_canonical(args.registry, args.source, args.data, args.seed, args.meta), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
