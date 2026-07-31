#!/usr/bin/env python3
"""Create deterministic review batches from the English-to-Vietnamese queue."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


FIELDS = ("sense_id", "meaning", "description", "examples", "collocations")
EMPTY_MEANINGS = {
    1000000158181: "luật số lớn mạnh",
    1000000005594: "ve chó Mỹ",
    1000000006699: "tiếng Anh-Pháp",
    1000000006855: "phim hoạt hình",
    1000000007242: "ăng-ten",
    1000000007243: "khả năng cảm nhận",
    1000000007244: "râu",
    1000000010759: "cá tuyết Đại Tây Dương",
}
POS_FALLBACKS = {"noun": "danh từ", "verb": "động từ", "adj": "tính từ", "adv": "trạng từ"}
WORD_RE = re.compile(r"[\wÀ-ỹ]+(?:-[\wÀ-ỹ]+)?", re.UNICODE)


VIETNAMESE_MARKERS = "\u0103\u00e2\u0111\u00ea\u00f4\u01a1\u01b0\u00e1\u00e0\u1ea3\u00e3\u1ea1\u1ea5\u1ea7\u1ea9\u1eab\u1ead\u1eaf\u1eb1\u1eb3\u1eb5\u1eb7\u00e9\u00e8\u1ebb\u1ebd\u1eb9\u1ebf\u1ec1\u1ec3\u1ec5\u1ec7\u00ed\u00ec\u1ec9\u0129\u1ecb\u00f3\u00f2\u1ecf\u00f5\u1ecd\u1ed1\u1ed3\u1ed5\u1ed7\u1ed9\u1edb\u1edd\u1edf\u1ee1\u1ee3\u00fa\u00f9\u1ee7\u0169\u1ee5\u1ee9\u1eeb\u1eed\u1eef\u1ef1\u00fd\u1ef3\u1ef7\u1ef9\u1ef5"


def words(value: str) -> list[str]:
    return WORD_RE.findall(value)


def is_concise_vietnamese(value: str) -> bool:
    tokens = words(value)
    return bool(value.strip()) and len(value) <= 35 and 1 <= len(tokens) <= 5 and any(
        char in "ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
        for char in value.casefold()
    )


def is_vietnamese(value: str) -> bool:
    return any(char in VIETNAMESE_MARKERS for char in value.casefold())


def fallback_meaning(row: dict[str, Any]) -> str:
    return EMPTY_MEANINGS.get(int(row["sense_id"]), POS_FALLBACKS.get(str(row.get("pos", "")), "nghĩa từ"))


def compact_meaning(value: str, pos: str) -> str:
    """Keep the semantic lead of a Vietnamese definition within the batch limit."""
    source = re.split(r"[;,(]", value, maxsplit=1)[0]
    tokens = words(source)
    if tokens[:3] == ["một", "trong", "các"]:
        tokens = tokens[3:]
    elif tokens[:2] in (["một", "loại"], ["một", "sự"], ["một", "người"], ["một", "đơn"]):
        tokens = tokens[1:]
    elif tokens[:1] == ["một"]:
        tokens = tokens[1:]
    result = " ".join(tokens[:5]).strip()
    while result and len(result) > 35:
        result = " ".join(words(result)[:-1])
    return result or POS_FALLBACKS.get(pos, "nghĩa từ")


def normalize_description(gloss: list[Any]) -> str:
    return " ".join(" ".join(str(item).split()) for item in gloss).strip()


def build_record(row: dict[str, Any]) -> tuple[dict[str, Any], str]:
    current = str(row.get("current_meaning", "")).strip()
    if is_concise_vietnamese(current):
        meaning, status = current, "preserved"
    elif is_vietnamese(current):
        meaning, status = compact_meaning(current, str(row.get("pos", ""))), "compacted"
    else:
        meaning = fallback_meaning(row)
        status = "filled_empty"
    return ({
        "sense_id": int(row["sense_id"]),
        "meaning": meaning,
        "description": normalize_description(row.get("gloss", [])),
        "examples": row["examples"],
        "collocations": row["collocations"],
    }, status)


def build_batches(queue_path: Path, output_dir: Path, batch_size: int = 250) -> dict[str, int]:
    if not 1 <= batch_size <= 250:
        raise ValueError("batch_size must be between 1 and 250")
    rows = [json.loads(line) for line in queue_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    output_dir.mkdir(parents=True, exist_ok=True)
    for path in output_dir.glob("batch-*.jsonl"):
        path.unlink()
    records: list[dict[str, Any]] = []
    counts = {"preserved": 0, "compacted": 0, "filled_empty": 0}
    for row in rows:
        record, status = build_record(row)
        records.append(record)
        counts[status] += 1
    for index in range(0, len(records), batch_size):
        path = output_dir / f"batch-{index // batch_size + 1:03d}.jsonl"
        path.write_text("".join(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n" for record in records[index:index + batch_size]), encoding="utf-8")
    return {"batches": (len(records) + batch_size - 1) // batch_size, "records": len(records), **counts}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, default=Path("packs/en/trans-vi/review/queue.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("packs/en/trans-vi/review/batches"))
    parser.add_argument("--batch-size", type=int, default=250)
    args = parser.parse_args()
    print(json.dumps(build_batches(args.queue, args.output_dir, args.batch_size), ensure_ascii=False))


if __name__ == "__main__":
    main()
