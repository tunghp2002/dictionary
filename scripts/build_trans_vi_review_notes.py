#!/usr/bin/env python3
"""Write a review queue for translation meanings that look too verbose."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ENCYCLOPEDIC = re.compile(
    r"\b(được định nghĩa|phát minh|thế kỷ|thường được|có nguồn gốc)\b",
    re.IGNORECASE,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("packs/en/trans-vi/data.jsonl"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("packs/en/trans-vi/notes-review.jsonl"),
    )
    parser.add_argument("--max-length", type=int, default=45)
    args = parser.parse_args()

    notes: list[dict[str, object]] = []
    for line in args.input.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        meaning = str(record.get("meaning", "")).strip()
        if not meaning:
            continue

        reasons: list[str] = []
        if len(meaning) > args.max_length:
            reasons.append("long_meaning")
        if any(char in meaning for char in "();:"):
            reasons.append("definition_punctuation")
        if ENCYCLOPEDIC.search(meaning):
            reasons.append("encyclopedic_phrase")
        if not reasons:
            continue

        notes.append(
            {
                "sense_id": int(record["sense_id"]),
                "reasons": reasons,
                "current_meaning": meaning,
            }
        )

    notes.sort(key=lambda item: int(item["sense_id"]))
    args.output.write_text(
        "".join(
            json.dumps(note, ensure_ascii=False, separators=(",", ":")) + "\n"
            for note in notes
        ),
        encoding="utf-8",
    )
    print(f"wrote {len(notes)} review notes to {args.output}")


if __name__ == "__main__":
    main()
