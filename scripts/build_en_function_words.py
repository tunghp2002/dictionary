#!/usr/bin/env python3
"""Assign stable IDs to the curated English function-word supplement."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.build_core_en import load_id_registry, write_id_registry, write_jsonl
except ModuleNotFoundError:  # direct `python scripts/build_en_function_words.py`
    from build_core_en import load_id_registry, write_id_registry, write_jsonl


REQUIRED_FIELDS = {
    "source_key",
    "word",
    "pos",
    "category",
    "priority",
    "description_hint",
    "usage_hint",
}
ALLOWED_CATEGORIES = {
    "pronoun", "article", "determiner", "quantifier", "distributive",
    "preposition", "conjunction", "auxiliary", "modal", "negator",
    "particle", "discourse_adverb", "contraction", "adv",
}
OPTIONAL_FIELDS = {"register"}


def load_function_words(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    source_keys: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"invalid JSON on line {line_number}") from error
        if not isinstance(row, dict) or not REQUIRED_FIELDS <= set(row) <= REQUIRED_FIELDS | OPTIONAL_FIELDS:
            raise ValueError(f"invalid fields on line {line_number}")
        if not all(isinstance(row[field], str) and row[field].strip() for field in REQUIRED_FIELDS - {"priority"}):
            raise ValueError(f"blank required field on line {line_number}")
        if not isinstance(row["priority"], int) or isinstance(row["priority"], bool) or row["priority"] < 0:
            raise ValueError(f"invalid priority on line {line_number}")
        source_key = row["source_key"]
        if source_key in source_keys:
            raise ValueError(f"duplicate source_key: {source_key}")
        if not source_key.startswith("supplement:function:"):
            raise ValueError(f"invalid source_key: {source_key}")
        if row["category"] not in ALLOWED_CATEGORIES:
            raise ValueError(f"prohibited category: {row['category']}")
        if "register" in row and row["register"] != "informal":
            raise ValueError(f"invalid register: {row['register']}")
        if row["category"] == "contraction" and "'" not in row["word"] and row.get("register") != "informal":
            raise ValueError(f"invalid contraction spelling: {row['word']}")
        source_keys.add(source_key)
        rows.append(row)
    return rows


def build_function_word_queue(table_path: Path, registry_path: Path) -> tuple[list[dict], dict[str, int]]:
    rows = load_function_words(table_path)
    registry = load_id_registry(registry_path)
    next_id = max(registry.values(), default=1_000_000_000_000) + 1
    ordered_rows = sorted(rows, key=lambda row: (row["priority"], row["word"].casefold(), row["source_key"]))
    for row in ordered_rows:
        sense_id = registry.get(row["source_key"])
        if sense_id is None:
            sense_id = next_id
            registry[row["source_key"]] = sense_id
            next_id += 1
        row["sense_id"] = sense_id
    return ordered_rows, registry


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", type=Path, default=Path("packs/en/core/function-words.jsonl"))
    parser.add_argument("--registry", type=Path, default=Path("packs/en/core/sense-ids.tsv"))
    parser.add_argument("--queue", type=Path, required=True)
    args = parser.parse_args()
    rows, registry = build_function_word_queue(args.table, args.registry)
    write_id_registry(args.registry, registry)
    write_jsonl(args.queue, rows)


if __name__ == "__main__":
    main()
