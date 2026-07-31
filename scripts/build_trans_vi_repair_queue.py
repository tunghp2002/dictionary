#!/usr/bin/env python3
"""Create a review queue for empty or non-concise Vietnamese meanings."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.build_trans_vi_batches import is_concise_vietnamese
except ModuleNotFoundError:
    from build_trans_vi_batches import is_concise_vietnamese


FIELDS = ("sense_id", "word", "pos", "gloss", "current_meaning", "examples", "collocations")


def build_repair_queue(queue_path: Path, manifest_path: Path, output_path: Path) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target_ids = {int(sense_id) for sense_id in manifest["target_sense_ids"]}
    records: list[dict[str, Any]] = []
    for line in queue_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if int(row["sense_id"]) in target_ids and not is_concise_vietnamese(str(row.get("current_meaning", ""))):
            records.append({field: row[field] for field in FIELDS})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records),
        encoding="utf-8",
    )
    return len(records)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, default=Path("packs/en/trans-vi/review/queue.jsonl"))
    parser.add_argument("--manifest", type=Path, default=Path("packs/en/trans-vi/target-manifest.json"))
    parser.add_argument("--output", type=Path, default=Path("packs/en/trans-vi/review/repair-queue.jsonl"))
    args = parser.parse_args()
    print(json.dumps({"records": build_repair_queue(args.queue, args.manifest, args.output)}))


if __name__ == "__main__":
    main()
