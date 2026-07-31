#!/usr/bin/env python3
"""Build an OEWN-only queue for fresh Vietnamese translation generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.build_core_en import load_id_registry
    from scripts.build_trans_vi_target import EXPECTED_TARGET_SENSES, select_target_words
    from scripts.fill_trans_vi_deepseek import load_oewn_context
except ModuleNotFoundError:  # direct `python scripts/build_trans_vi_clean_queue.py`
    from build_core_en import load_id_registry
    from build_trans_vi_target import EXPECTED_TARGET_SENSES, select_target_words
    from fill_trans_vi_deepseek import load_oewn_context


QUEUE_FIELDS = ("sense_id", "word", "pos", "gloss")


def build_clean_queue(core_path: Path, oewn_yaml: Path, output_path: Path) -> int:
    """Write target senses using OEWN context only, without legacy translation data."""
    registry_path = core_path.with_name("sense-ids.tsv")
    if not registry_path.exists():
        raise FileNotFoundError(f"Missing core ID registry: {registry_path}")
    source_keys = {numeric_id: key for key, numeric_id in load_id_registry(registry_path).items()}
    context = load_oewn_context(oewn_yaml)
    seen_ids: set[int] = set()
    queue: list[dict[str, Any]] = []
    for record in select_target_words(core_path):
        for sense in record["senses"]:
            sense_id = int(sense["id"])
            if sense_id in seen_ids:
                continue
            seen_ids.add(sense_id)
            item = context.get(source_keys.get(sense_id, ""))
            if item is None:
                raise RuntimeError(f"Missing OEWN context for target sense {sense_id}")
            queue.append({field: item["definitions"] if field == "gloss" else sense_id if field == "sense_id" else item[field] for field in QUEUE_FIELDS})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in queue),
        encoding="utf-8",
    )
    return len(queue)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core", type=Path, default=Path("packs/en/core/data.jsonl"))
    parser.add_argument("--oewn-yaml", type=Path, default=Path(".cache/sources/oewn-2025/src/yaml"))
    parser.add_argument("--output", type=Path, default=Path("packs/en/trans-vi/review/clean-queue.jsonl"))
    args = parser.parse_args()
    count = build_clean_queue(args.core, args.oewn_yaml, args.output)
    if count != EXPECTED_TARGET_SENSES:
        raise SystemExit(f"Expected {EXPECTED_TARGET_SENSES} target senses, got {count}")
    print(count)


if __name__ == "__main__":
    main()
