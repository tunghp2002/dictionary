#!/usr/bin/env python3
"""Build the deterministic top-30,000 English target and OEWN review queue."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from scripts.build_core_en import load_id_registry
    from scripts.fill_trans_vi_deepseek import load_oewn_context
except ModuleNotFoundError:  # direct `python scripts/build_trans_vi_target.py`
    from build_core_en import load_id_registry
    from fill_trans_vi_deepseek import load_oewn_context


TARGET_LEMMAS = 30_000
EXPECTED_TARGET_SENSES = 57_446
QUEUE_FIELDS = (
    "sense_id",
    "word",
    "pos",
    "gloss",
    "current_meaning",
    "description",
    "examples",
    "collocations",
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def select_target_words(core_path: Path, limit: int = TARGET_LEMMAS) -> list[dict[str, Any]]:
    """Return the most frequent core lemmas with deterministic tie ordering."""
    records = read_jsonl(core_path)
    return sorted(
        records,
        key=lambda record: (record.get("frequency", float("inf")), record["word"].casefold()),
    )[:limit]


def load_translations(path: Path) -> dict[int, dict[str, Any]]:
    if not path.exists():
        return {}
    return {int(record["sense_id"]): record for record in read_jsonl(path)}


def build_target_manifest(
    core_path: Path,
    translation_path: Path,
    oewn_yaml: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Write target IDs, provenance, and the adjacent OEWN translation queue."""
    selected = select_target_words(core_path)
    target_ids: list[int] = []
    seen_ids: set[int] = set()
    for record in selected:
        for sense in record["senses"]:
            sense_id = int(sense["id"])
            if sense_id not in seen_ids:
                target_ids.append(sense_id)
                seen_ids.add(sense_id)

    registry_path = core_path.with_name("sense-ids.tsv")
    if not registry_path.exists():
        raise FileNotFoundError(f"Missing core ID registry: {registry_path}")
    source_keys = {numeric_id: source_key for source_key, numeric_id in load_id_registry(registry_path).items()}
    context = load_oewn_context(oewn_yaml)
    translations = load_translations(translation_path)

    queue: list[dict[str, Any]] = []
    for sense_id in target_ids:
        source_key = source_keys.get(sense_id)
        item = context.get(source_key or "")
        if item is None:
            raise RuntimeError(f"Missing OEWN context for target sense {sense_id}")
        translation = translations.get(sense_id, {})
        queue.append(
            {
                "sense_id": sense_id,
                "word": item["word"],
                "pos": item["pos"],
                "gloss": item["definitions"],
                "current_meaning": str(translation.get("meaning", "")).strip(),
                "description": translation.get("description", ""),
                "examples": translation.get("examples", []),
                "collocations": translation.get("collocations", []),
            }
        )

    queue_path = output_path.parent / "review" / "queue.jsonl"
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(
        "".join(json.dumps(item, ensure_ascii=False, separators=(",", ":")) + "\n" for item in queue),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "target_lemmas": len(selected),
        "target_senses": len(target_ids),
        "target_sense_ids": target_ids,
        "sources": {
            "core": core_path.as_posix(),
            "translations": translation_path.as_posix(),
            "oewn_yaml": oewn_yaml.as_posix(),
        },
        "queue": {"path": queue_path.as_posix(), "fields": list(QUEUE_FIELDS)},
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--core", type=Path, default=Path("packs/en/core/data.jsonl"))
    parser.add_argument("--translations", type=Path, default=Path("packs/en/trans-vi/data.jsonl"))
    parser.add_argument("--oewn-yaml", type=Path, default=Path(".cache/sources/oewn-2025/src/yaml"))
    parser.add_argument("--output", type=Path, default=Path("packs/en/trans-vi/target-manifest.json"))
    args = parser.parse_args()
    manifest = build_target_manifest(args.core, args.translations, args.oewn_yaml, args.output)
    if manifest["target_senses"] != EXPECTED_TARGET_SENSES:
        raise SystemExit(f"Expected {EXPECTED_TARGET_SENSES} target senses, got {manifest['target_senses']}")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
