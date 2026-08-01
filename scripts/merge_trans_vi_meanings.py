#!/usr/bin/env python3
"""Apply validated meaning-only AI batches while preserving every sense ID."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def merge_meanings(batch_paths: list[Path], data_path: Path) -> int:
    meanings: dict[int, str] = {}
    for path in batch_paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if set(row) != {"sense_id", "meaning"}:
                raise ValueError(f"{path}: expected sense_id/meaning only")
            sense_id = int(row["sense_id"])
            meaning = str(row["meaning"]).strip()
            if not meaning or len(meaning.split()) > 5 or len(meaning) > 35:
                raise ValueError(f"{path}: invalid meaning for {sense_id}")
            if sense_id in meanings and meanings[sense_id] != meaning:
                raise ValueError(f"conflicting meaning for {sense_id}")
            meanings[sense_id] = meaning

    records = [json.loads(line) for line in data_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    known = {int(row["sense_id"]): row for row in records}
    unknown = set(meanings) - set(known)
    if unknown:
        raise ValueError(f"unknown sense IDs: {sorted(unknown)[:5]}")
    for sense_id, meaning in meanings.items():
        known[sense_id]["meaning"] = meaning
        known[sense_id]["description"] = ""
        known[sense_id]["examples"] = []
        known[sense_id]["collocations"] = []
    temporary = data_path.with_suffix(data_path.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(known[sense_id], ensure_ascii=False, separators=(",", ":")) + "\n" for sense_id in sorted(known)),
        encoding="utf-8",
    )
    temporary.replace(data_path)
    return len(meanings)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("packs/en/trans-vi/data.jsonl"))
    parser.add_argument("--batch", action="append", type=Path, required=True)
    args = parser.parse_args()
    print(merge_meanings(args.batch, args.data))


if __name__ == "__main__":
    main()
