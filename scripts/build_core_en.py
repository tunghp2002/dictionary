#!/usr/bin/env python3
"""Convert pinned open English lexical data to the core-en JSONL schema."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import yaml


MAX_SAFE_INTEGER = (1 << 53) - 1
LANGUAGE_NAMESPACE = 1
LOCAL_ID_BASE = 10**12
MAX_LANGUAGE_NAMESPACE = 999
MAX_LOCAL_ID = LOCAL_ID_BASE - 1
POS_NAMES = {
    "n": "noun",
    "v": "verb",
    "a": "adj",
    "s": "adj",
    "r": "adv",
}
VERB_GRAMMAR_ORDER = ("transitive", "intransitive", "linking")
LINKING_SUBCATS = {"via-adj", "vii-adj"}
OEWN_RELEASE = "2025-edition"
OEWN_COMMIT = "dc343f2683279ecbb13fab4e2fd778d7b162d287"


def sense_id(local_id: int, namespace: int = LANGUAGE_NAMESPACE) -> int:
    if not 1 <= namespace <= MAX_LANGUAGE_NAMESPACE:
        raise ValueError(f"Language namespace must be 1..{MAX_LANGUAGE_NAMESPACE}")
    if not 1 <= local_id <= MAX_LOCAL_ID:
        raise ValueError(f"Local sense ID must be 1..{MAX_LOCAL_ID}")
    value = namespace * LOCAL_ID_BASE + local_id
    if value > MAX_SAFE_INTEGER:
        raise ValueError(f"Sense ID {value} exceeds JavaScript's safe integer range")
    return value


def format_ipa(value: str) -> str:
    value = value.strip().strip("/")
    return f"/{value}/"


def load_entries(entries_dir: Path) -> tuple[list[dict[str, Any]], set[str]]:
    words: dict[str, dict[str, Any]] = {}
    source_keys: set[str] = set()
    source_words: dict[str, str] = {}
    synset_words: dict[str, set[str]] = defaultdict(set)
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

    entry_files = sorted(entries_dir.glob("entries-*.yaml"))
    if not entry_files:
        raise FileNotFoundError(f"No entries-*.yaml files found in {entries_dir}")

    for path in entry_files:
        print(f"Reading {path.name}...")
        with path.open(encoding="utf-8") as handle:
            source_entries = yaml.load(handle, Loader=loader)
        for word, parts in source_entries.items():
            record = words.setdefault(word, {"word": word, "senses": [], "_ipas": []})
            for source_pos, part in parts.items():
                pos = POS_NAMES.get(source_pos.split("-", 1)[0])
                if pos is None:
                    continue
                for pronunciation in part.get("pronunciation", ()):
                    ipa = format_ipa(pronunciation.get("value", ""))
                    if ipa != "//" and ipa not in record["_ipas"]:
                        record["_ipas"].append(ipa)
                for sense in part.get("sense", ()):
                    source_key = str(sense["id"])
                    synset = str(sense["synset"])
                    if source_key in source_keys:
                        raise RuntimeError(f"Duplicate source sense key: {source_key!r}")
                    source_keys.add(source_key)
                    source_words[source_key] = word
                    synset_words[synset].add(word)
                    record["senses"].append(
                        {
                            "_source_key": source_key,
                            "_synset": synset,
                            "_antonym_keys": list(sense.get("antonym", ())),
                            "_subcats": list(sense.get("subcat", ())),
                            "pos": pos,
                        }
                    )

    for record in words.values():
        for sense in record["senses"]:
            sense["_synonyms"] = sorted(
                {
                    value
                    for value in synset_words[sense["_synset"]]
                    if value.casefold() != record["word"].casefold()
                },
                key=lambda value: (value.casefold(), value),
            )
            sense["_antonyms"] = sorted(
                {
                    source_words[key]
                    for key in sense.pop("_antonym_keys")
                    if key in source_words
                    and source_words[key].casefold() != record["word"].casefold()
                },
                key=lambda value: (value.casefold(), value),
            )

    return (
        sorted(words.values(), key=lambda item: (item["word"].casefold(), item["word"])),
        source_keys,
    )


def grammar_from_subcats(pos: str, subcats: Iterable[str]) -> dict[str, list[str]]:
    """Reduce OEWN verb frames to user-facing transitivity labels."""
    if pos != "verb":
        return {}
    subcats = set(subcats)
    labels: set[str] = set()
    if any(
        frame == "ditransitive"
        or frame.startswith(("vtaa", "vtai", "vtia", "vtii"))
        for frame in subcats
    ):
        labels.add("transitive")
    if any(frame in LINKING_SUBCATS for frame in subcats):
        labels.add("linking")
    if any(
        frame.startswith(("via", "vii", "vibody", "nonreferential"))
        and frame not in LINKING_SUBCATS
        for frame in subcats
    ):
        labels.add("intransitive")
    ordered = [label for label in VERB_GRAMMAR_ORDER if label in labels]
    return {"verb_type": ordered} if ordered else {}


def load_id_registry(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    registry: dict[str, int] = {}
    used_ids: set[int] = set()
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            source_key = row["source_key"]
            numeric_id = int(row["sense_id"])
            local_id = numeric_id - LANGUAGE_NAMESPACE * LOCAL_ID_BASE
            if sense_id(local_id) != numeric_id:
                raise RuntimeError(f"Invalid English sense ID in registry: {numeric_id}")
            if source_key in registry or numeric_id in used_ids:
                raise RuntimeError(f"Duplicate registry entry: {source_key!r}, {numeric_id}")
            registry[source_key] = numeric_id
            used_ids.add(numeric_id)
    return registry


def assign_sense_ids(
    records: list[dict[str, Any]],
    registry: dict[str, int],
) -> None:
    next_local_id = max(
        (
            numeric_id - LANGUAGE_NAMESPACE * LOCAL_ID_BASE
            for numeric_id in registry.values()
        ),
        default=0,
    )
    for record in records:
        for sense in record["senses"]:
            source_key = sense.pop("_source_key")
            sense.pop("_synset", None)
            subcats = sense.pop("_subcats", ())
            synonyms = sense.pop("_synonyms", ())
            antonyms = sense.pop("_antonyms", ())
            numeric_id = registry.get(source_key)
            if numeric_id is None:
                next_local_id += 1
                numeric_id = sense_id(next_local_id)
                registry[source_key] = numeric_id
            pos = sense["pos"]
            sense.clear()
            sense.update({"id": numeric_id, "pos": pos})
            if synonyms:
                sense["synonyms"] = synonyms
            if antonyms:
                sense["antonyms"] = antonyms
            grammar = grammar_from_subcats(pos, subcats)
            if grammar:
                sense["grammar"] = grammar
        record["senses"].sort(key=lambda sense: sense["id"])


def write_id_registry(path: Path, registry: dict[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(("sense_id", "source_key"))
        for source_key, numeric_id in sorted(
            registry.items(), key=lambda item: item[1]
        ):
            writer.writerow((numeric_id, source_key))


def add_frequency_ranks(
    records: list[dict[str, Any]],
    frequency: Callable[[str], float],
) -> None:
    scores = [
        (frequency(record["word"]), record["word"].casefold(), record["word"], record)
        for record in records
    ]
    ranked = (item for item in sorted(scores, key=lambda item: (-item[0], item[1], item[2])) if item[0] > 0)
    for rank, (_, _, _, record) in enumerate(ranked, start=1):
        record["frequency"] = rank


def finalize_records(records: list[dict[str, Any]]) -> None:
    for record in records:
        ipas = record.pop("_ipas")
        if ipas:
            record["ipa"] = ipas[0]
        ordered: dict[str, Any] = {"word": record["word"]}
        for key in ("ipa", "frequency", "senses"):
            if key in record:
                ordered[key] = record[key]
        record.clear()
        record.update(ordered)


def write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            handle.write("\n")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(
    oewn_dir: Path,
    output: Path,
    metadata_output: Path,
    id_registry: Path,
    include_frequency: bool = True,
) -> dict[str, Any]:
    records, source_keys = load_entries(oewn_dir / "src/yaml")
    registry = load_id_registry(id_registry)
    assign_sense_ids(records, registry)
    if include_frequency:
        try:
            from wordfreq import zipf_frequency
        except ImportError as error:
            raise RuntimeError(
                "wordfreq is required; install requirements-build.txt or use --no-frequency"
            ) from error
        print("Calculating frequency ranks...")
        add_frequency_ranks(records, lambda word: zipf_frequency(word, "en"))

    finalize_records(records)
    write_jsonl(output, records)
    write_id_registry(id_registry, registry)
    metadata = {
        "schema_version": 5,
        "key_path": "word",
        "sense_id": {
            "format": "namespace * 10^12 + local_id",
            "language": "en",
            "namespace": LANGUAGE_NAMESPACE,
            "registry": id_registry.as_posix(),
        },
        "license": "CC-BY-SA-4.0",
        "attribution": "DATA_LICENSES.md",
        "records": len(records),
        "senses": len(source_keys),
        "reserved_sense_ids": len(registry),
        "with_ipa": sum("ipa" in record for record in records),
        "with_frequency": sum("frequency" in record for record in records),
        "senses_with_grammar": sum(
            "grammar" in sense
            for record in records
            for sense in record["senses"]
        ),
        "senses_with_synonyms": sum(
            "synonyms" in sense for record in records for sense in record["senses"]
        ),
        "senses_with_antonyms": sum(
            "antonyms" in sense for record in records for sense in record["senses"]
        ),
        "schema": "packs/en/core/schema.json",
        "sources": {
            "open_english_wordnet": {
                "release": OEWN_RELEASE,
                "commit": OEWN_COMMIT,
            },
            "wordfreq": "3.1.1" if include_frequency else None,
        },
        "output": {
            "path": output.as_posix(),
            "sha256": file_sha256(output),
            "bytes": output.stat().st_size,
        },
    }
    metadata_output.parent.mkdir(parents=True, exist_ok=True)
    metadata_output.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return metadata


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--oewn-dir",
        type=Path,
        default=Path(".cache/sources/oewn-2025"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("packs/en/core/data.jsonl"),
    )
    parser.add_argument(
        "--metadata-output",
        type=Path,
        default=Path("packs/en/core/meta.json"),
    )
    parser.add_argument(
        "--id-registry",
        type=Path,
        default=Path("packs/en/core/sense-ids.tsv"),
    )
    parser.add_argument("--no-frequency", action="store_true")
    args = parser.parse_args()
    metadata = build(
        args.oewn_dir,
        args.output,
        args.metadata_output,
        args.id_registry,
        include_frequency=not args.no_frequency,
    )
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
