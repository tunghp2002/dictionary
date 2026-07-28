#!/usr/bin/env python3
"""Optionally build a bulk English-to-Vietnamese import from OMW data.

The checked-in ``packs/en/trans-vi/data.jsonl`` is a curated seed. Keep this
importer's output separate so a bulk refresh cannot overwrite that seed.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from scripts.build_core_en import file_sha256, load_id_registry, write_jsonl
except ModuleNotFoundError:  # direct `python scripts/build_trans_vi.py`
    from build_core_en import file_sha256, load_id_registry, write_jsonl


OMW_COMMIT = "406bf83b3c507a3d1f26e88252d5d66893fd36bf"
OMW_RELATIVE_PATH = "wns/wikt/wn-wikt-vie.tab"
CJK_RANGES = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF))
PWN_POS = {"1": "n", "2": "v", "3": "a", "4": "r", "5": "a"}


def normalize_synset(raw_synset: Any, source_pos: str) -> str:
    value = str(raw_synset)
    if "-" in value:
        offset, pos = value.rsplit("-", 1)
    else:
        offset, pos = value, source_pos
    pos = {"s": "a"}.get(pos, pos)
    if pos not in {"n", "v", "a", "r"}:
        raise ValueError(f"Unsupported synset POS: {raw_synset!r}")
    return f"{int(offset):08d}-{pos}"


def load_pwn30_sense_synsets(index_sense: Path) -> dict[str, str]:
    sense_synsets: dict[str, str] = {}
    with index_sense.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip() or line.startswith(" "):
                continue
            fields = line.split()
            if len(fields) < 3:
                continue
            source_key, offset = fields[:2]
            pos = PWN_POS.get(source_key.split("%", 1)[1][:1])
            if pos:
                sense_synsets[source_key] = f"{int(offset):08d}-{pos}"
    return sense_synsets


def has_cjk(value: str) -> bool:
    return any(start <= ord(char) <= end for char in value for start, end in CJK_RANGES)


def normalize_meaning(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def load_vietnamese_lemmas(path: Path) -> dict[str, list[str]]:
    meanings: dict[str, list[str]] = defaultdict(list)
    seen: dict[str, set[str]] = defaultdict(set)
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip() or line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 3 or fields[1] != "vie:lemma":
                continue
            meaning = normalize_meaning(fields[2])
            if not meaning or has_cjk(meaning):
                continue
            key = meaning.casefold()
            if key not in seen[fields[0]]:
                seen[fields[0]].add(key)
                meanings[fields[0]].append(meaning)
    return dict(meanings)


def build_translation(
    core_registry: Path,
    pwn30_index_sense: Path,
    vietnamese_tab: Path,
    output: Path,
    metadata_output: Path,
) -> dict[str, Any]:
    registry = load_id_registry(core_registry)
    pwn30_synsets = load_pwn30_sense_synsets(pwn30_index_sense)
    synset_meanings = load_vietnamese_lemmas(vietnamese_tab)
    records: list[dict[str, Any]] = []
    for source_key, numeric_id in sorted(registry.items(), key=lambda item: item[1]):
        # OMW uses Princeton WordNet 3.0 offsets; OEWN 2025 uses 3.1 offsets.
        # Permanent sense keys bridge the two releases where the key exists.
        synset = pwn30_synsets.get(source_key)
        if synset is None:
            continue
        meanings = synset_meanings.get(synset)
        if not meanings:
            continue
        records.append({"sense_id": numeric_id, "meaning": ", ".join(meanings)})

    write_jsonl(output, records)
    metadata = {
        "schema_version": 1,
        "key_path": "sense_id",
        "source_language": "en",
        "target_language": "vi",
        "license": "CC-BY-SA-3.0",
        "attribution": "See DATA_LICENSES.md",
        "records": len(records),
        "core_senses": len(registry),
        "coverage": len(records) / len(registry) if registry else 0,
        "fields": ["sense_id", "meaning"],
        "sources": {
            "omw_data": {
                "commit": OMW_COMMIT,
                "file": OMW_RELATIVE_PATH,
                "license": "CC-BY-SA-3.0 (Wiktionary-derived data)",
            }
        },
        "output": {
            "path": output.as_posix(),
            "sha256": file_sha256(output),
            "bytes": output.stat().st_size,
        },
    }
    metadata_output.parent.mkdir(parents=True, exist_ok=True)
    metadata_output.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-registry", type=Path, default=Path("packs/en/core/sense-ids.tsv"))
    parser.add_argument(
        "--pwn30-index-sense",
        type=Path,
        default=Path(".cache/sources/pwn30/index.sense"),
    )
    parser.add_argument(
        "--vietnamese-tab",
        type=Path,
        default=Path(".cache/sources/omw-data/wns/wikt/wn-wikt-vie.tab"),
    )
    parser.add_argument(
        "--output", type=Path, default=Path("packs/en/trans-vi/omw-data.jsonl")
    )
    parser.add_argument(
        "--metadata-output", type=Path, default=Path("packs/en/trans-vi/omw-meta.json")
    )
    args = parser.parse_args()
    metadata = build_translation(
        args.core_registry,
        args.pwn30_index_sense,
        args.vietnamese_tab,
        args.output,
        args.metadata_output,
    )
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
