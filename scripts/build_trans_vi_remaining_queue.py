#!/usr/bin/env python3
"""Build an OEWN-only queue for canonical senses without Vietnamese meanings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.build_core_en import load_id_registry, write_jsonl
    from scripts.fill_trans_vi_deepseek import load_oewn_context
except ModuleNotFoundError:  # direct `python scripts/build_trans_vi_remaining_queue.py`
    from build_core_en import load_id_registry, write_jsonl
    from fill_trans_vi_deepseek import load_oewn_context


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_remaining_queue(
    registry_path: Path, data_path: Path, oewn_yaml: Path, output_path: Path
) -> int:
    registry = load_id_registry(registry_path)
    existing = {int(row["sense_id"]): str(row.get("meaning", "")).strip() for row in read_jsonl(data_path)}
    if set(existing) != set(registry.values()):
        raise RuntimeError("canonical IDs and registry IDs differ")
    context = load_oewn_context(oewn_yaml)
    rows = []
    for source_key, sense_id in sorted(registry.items(), key=lambda item: item[1]):
        if existing[sense_id]:
            continue
        item = context.get(source_key)
        if item is None:
            raise RuntimeError(f"Missing OEWN context for remaining sense {sense_id}")
        gloss = item["definitions"]
        if not gloss:
            raise RuntimeError(f"Missing OEWN gloss for remaining sense {sense_id}")
        rows.append({"sense_id": sense_id, "word": item["word"], "pos": item["pos"], "gloss": gloss})
    write_jsonl(output_path, rows)
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, default=Path("packs/en/core/sense-ids.tsv"))
    parser.add_argument("--data", type=Path, default=Path("packs/en/trans-vi/data.jsonl"))
    parser.add_argument("--oewn-yaml", type=Path, default=Path(".cache/sources/oewn-2025/src/yaml"))
    parser.add_argument("--output", type=Path, default=Path("packs/en/trans-vi/review/remaining-queue.jsonl"))
    args = parser.parse_args()
    print(build_remaining_queue(args.registry, args.data, args.oewn_yaml, args.output))


if __name__ == "__main__":
    main()
