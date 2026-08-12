#!/usr/bin/env python3
"""Merge curated English function-word senses into the core JSONL index."""

from __future__ import annotations

import json
import os
import tempfile
from hashlib import sha256
from pathlib import Path
from typing import Any

try:
    from scripts.build_core_en import load_id_registry
    from scripts.build_en_function_words import load_function_words
except ModuleNotFoundError:  # direct script execution
    from build_core_en import load_id_registry
    from build_en_function_words import load_function_words


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSON in core data on line {line_number}") from error
        if not isinstance(record, dict) or not isinstance(record.get("word"), str):
            raise ValueError(f"invalid core record on line {line_number}")
        if not isinstance(record.get("senses"), list):
            raise ValueError(f"invalid core senses on line {line_number}")
        records.append(record)
    return records


def _write_jsonl_atomically(path: Path, records: list[dict[str, Any]]) -> None:
    payload = "".join(
        json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
        for record in records
    )
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False, newline=""
    ) as handle:
        temporary = Path(handle.name)
        handle.write(payload)
    try:
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _refresh_metadata(meta_path: Path, core_path: Path, records: list[dict[str, Any]], registry: dict[str, int]) -> None:
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    payload = core_path.read_bytes()
    metadata["records"] = len(records)
    metadata["senses"] = sum(len(record["senses"]) for record in records)
    metadata["reserved_sense_ids"] = len(registry)
    metadata["with_frequency"] = sum("frequency" in record for record in records)
    metadata["output"]["sha256"] = sha256(payload).hexdigest()
    metadata["output"]["bytes"] = len(payload)
    temporary = meta_path.with_suffix(meta_path.suffix + ".tmp")
    try:
        temporary.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, meta_path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def merge_function_words_into_core(
    core_path: Path, function_words_path: Path, registry_path: Path, meta_path: Path | None = None
) -> int:
    """Merge function-word senses into core data and return the source-row count."""
    rows = load_function_words(function_words_path)
    registry = load_id_registry(registry_path)
    source_ids: dict[str, int] = {}
    for row in rows:
        source_key = row["source_key"]
        numeric_id = registry.get(source_key)
        if numeric_id is None:
            raise ValueError(f"missing registry ID for {source_key}")
        source_ids[source_key] = numeric_id

    records = _read_jsonl(core_path)
    by_word: dict[str, list[dict[str, Any]]] = {}
    id_owners: dict[int, str] = {}
    for record in records:
        key = record["word"].casefold()
        by_word.setdefault(key, []).append(record)
        for sense in record["senses"]:
            if not isinstance(sense, dict) or not isinstance(sense.get("id"), int):
                raise ValueError(f"invalid core sense for {record['word']}")
            numeric_id = sense["id"]
            owner = id_owners.setdefault(numeric_id, key)
            if owner != key:
                raise ValueError(f"core ID {numeric_id} is already owned by a different word")

    for row in rows:
        word = row["word"]
        key = word.casefold()
        numeric_id = source_ids[row["source_key"]]
        owner = id_owners.get(numeric_id)
        if owner is not None and owner != key:
            raise ValueError(f"core ID {numeric_id} is already owned by a different word")
        matches = by_word.get(key, [])
        record = next((item for item in matches if item["word"] == word), matches[0] if matches else None)
        if record is None:
            record = {"word": word, "frequency": row["priority"], "senses": []}
            records.append(record)
            by_word.setdefault(key, []).append(record)
        else:
            record["frequency"] = min(record.get("frequency", row["priority"]), row["priority"])
        sense = next((sense for sense in record["senses"] if sense["id"] == numeric_id), None)
        normalized_sense = {"id": numeric_id, "pos": row["category"]}
        if row.get("register") == "informal":
            normalized_sense["tags"] = {"register": ["informal"]}
        if sense is None:
            record["senses"].append(normalized_sense)
        else:
            sense.clear()
            sense.update(normalized_sense)
        id_owners[numeric_id] = key

    required_ids = set(source_ids.values())
    counts = {numeric_id: 0 for numeric_id in required_ids}
    for record in records:
        for sense in record["senses"]:
            if sense["id"] in counts:
                counts[sense["id"]] += 1
    duplicates = [numeric_id for numeric_id, count in counts.items() if count != 1]
    if duplicates:
        raise ValueError(f"supplemental ID must occur exactly once: {min(duplicates)}")

    records.sort(key=lambda record: (record["word"].casefold(), record["word"]))
    _write_jsonl_atomically(core_path, records)
    if meta_path is not None:
        _refresh_metadata(meta_path, core_path, records, registry)
    return len(rows)
