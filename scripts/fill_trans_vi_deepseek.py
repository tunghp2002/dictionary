#!/usr/bin/env python3
"""Fill concise Vietnamese meanings with DeepSeek using resumable concurrency."""

from __future__ import annotations

import argparse
import json
import os
import random
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import yaml


BASE_URL = "https://api.deepseek.com/chat/completions"
POS_NAMES = {"n": "noun", "v": "verb", "a": "adj", "s": "adj", "r": "adv"}
CJK_RANGES = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF))


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip().strip("'\""))


def load_oewn_context(oewn_yaml: Path) -> dict[str, dict[str, Any]]:
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    context: dict[str, dict[str, Any]] = {}
    entries: dict[str, dict[str, Any]] = {}
    for path in sorted(oewn_yaml.glob("entries-*.yaml")):
        with path.open(encoding="utf-8") as handle:
            source_entries = yaml.load(handle, Loader=loader) or {}
        for word, parts in source_entries.items():
            for source_pos, part in parts.items():
                pos = POS_NAMES.get(source_pos.split("-", 1)[0])
                if not pos:
                    continue
                for sense in part.get("sense", ()):
                    entries[str(sense["id"])] = {
                        "word": word,
                        "pos": pos,
                        "synset": str(sense.get("synset", "")),
                    }

    synsets: dict[str, dict[str, list[str]]] = {}
    for path in sorted(oewn_yaml.glob("*.yaml")):
        if path.name.startswith("entries-"):
            continue
        with path.open(encoding="utf-8") as handle:
            records = yaml.load(handle, Loader=loader) or {}
        for synset, record in records.items():
            if not isinstance(record, dict):
                continue
            synsets[str(synset)] = {
                "definitions": [str(value) for value in record.get("definition", ())],
                "examples": [str(value) for value in record.get("example", ())],
            }

    for source_key, entry in entries.items():
        gloss = synsets.get(entry["synset"], {})
        context[source_key] = {
            **entry,
            "definitions": gloss.get("definitions", []),
            "source_examples": gloss.get("examples", []),
        }
    return context


def load_registry(path: Path) -> dict[str, int]:
    registry: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        if line.strip():
            sense_id, source_key = line.split("\t", 1)
            registry[source_key] = int(sense_id)
    return registry


def load_core(path: Path) -> dict[str, dict[str, Any]]:
    return {
        record["word"]: record
        for record in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    }


def load_ids(path: Path) -> set[int]:
    if not path.exists():
        return set()
    return {int(json.loads(line)["sense_id"]) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def has_cjk(value: str) -> bool:
    return any(start <= ord(char) <= end for char in value for start, end in CJK_RANGES)


def translation_record(sense_id: int, meaning: str, record: dict[str, Any] | None = None) -> dict[str, Any]:
    record = record or {}
    return {
        "sense_id": sense_id,
        "meaning": meaning.strip(),
        "examples": record.get("examples", []),
        "collocations": record.get("collocations", []),
    }


def merge_seed(seed_path: Path, output_path: Path) -> None:
    records: dict[int, dict[str, Any]] = {}
    for path in (seed_path, output_path):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                if not has_cjk(record.get("meaning", "")):
                    numeric_id = int(record["sense_id"])
                    records[numeric_id] = translation_record(
                        numeric_id, record.get("meaning", ""), record
                    )
    seed_path.write_text(
        "".join(
            json.dumps(records[sense_id], ensure_ascii=False, separators=(",", ":")) + "\n"
            for sense_id in sorted(records)
        ),
        encoding="utf-8",
    )


def parse_json(content: str) -> dict[str, Any]:
    value = content.strip()
    if value.startswith("```"):
        value = value.split("\n", 1)[1].rsplit("```", 1)[0]
    result = json.loads(value)
    if not isinstance(result, dict):
        raise ValueError("DeepSeek response is not a JSON object")
    return result


def request_translation_group(api_key: str, items: list[dict[str, Any]], attempts: int = 4) -> list[dict[str, Any]]:
    prompt = {
        "senses": [
            {
                "sense_id": item["sense_id"],
                "word": item["word"],
                "pos": item["pos"],
                "gloss": item["definitions"],
                "source_examples": item["source_examples"],
            }
            for item in items
        ]
    }
    system = (
        "You are a bilingual dictionary editor, not an encyclopedic explainer. "
        "Translate each English dictionary sense into natural Vietnamese. "
        "Return JSON only as {items:[...]}; each item has exactly these keys: "
        "sense_id, meaning. meaning must normally be 1-5 Vietnamese words and "
        "at most 35 characters. Keep only the sense-defining semantic core. "
        "Do not include examples, history, origin, dates, mechanisms, geography, "
        "parenthetical explanations, or encyclopedic detail. Geography is allowed "
        "only when essential to the meaning itself. Do not merge senses or invent information."
    )
    body = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": system + " The response must be valid JSON."},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=False)},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": max(512, len(items) * 192),
        "temperature": 0.2,
        "stream": False,
        "thinking": {"type": "disabled"},
    }
    request = urllib.request.Request(
        BASE_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                payload = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"].get("content") or ""
            result = parse_json(content)
            raw_items = result.get("items")
            if not isinstance(raw_items, list):
                raise ValueError("items must be an array")
            expected_ids = {item["sense_id"] for item in items}
            output: list[dict[str, Any]] = []
            for raw_item in raw_items:
                sense_id = int(raw_item["sense_id"])
                meaning = raw_item.get("meaning")
                if not isinstance(meaning, str) or not meaning.strip():
                    raise ValueError(f"empty meaning for {sense_id}")
                if has_cjk(meaning):
                    raise ValueError(f"non-Vietnamese script in meaning for {sense_id}")
                if set(raw_item) != {"sense_id", "meaning"}:
                    raise ValueError(f"unexpected fields for {sense_id}")
                output.append(translation_record(sense_id, meaning))
            if {item["sense_id"] for item in output} != expected_ids:
                raise ValueError("response sense IDs do not match request")
            return output
        except (urllib.error.HTTPError, urllib.error.URLError, KeyError, ValueError, json.JSONDecodeError) as error:
            if attempt == attempts - 1:
                ids = ",".join(str(item["sense_id"]) for item in items)
                raise RuntimeError(f"senses {ids}: {error}") from error
            time.sleep((2**attempt) + random.random())
    raise AssertionError("unreachable")


def build_items(registry_path: Path, core_path: Path, oewn_yaml: Path, seed_path: Path, output_path: Path) -> list[dict[str, Any]]:
    registry = load_registry(registry_path)
    core = load_core(core_path)
    filled = load_ids(seed_path)
    done = load_ids(output_path)
    context = load_oewn_context(oewn_yaml)
    items = []
    for source_key, sense_id in registry.items():
        if sense_id in filled or sense_id in done or source_key not in context:
            continue
        item = {"sense_id": sense_id, **context[source_key]}
        item["priority"] = core.get(item["word"], {}).get("frequency", 10**9)
        items.append(item)
    items.sort(key=lambda item: (item["priority"], item["word"].casefold(), item["sense_id"]))
    return items


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=Path(".env"))
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=25)
    parser.add_argument("--group-size", type=int, default=8)
    parser.add_argument("--output", type=Path, default=Path(".cache/deepseek/meanings.jsonl"))
    parser.add_argument("--registry", type=Path, default=Path("packs/en/core/sense-ids.tsv"))
    parser.add_argument("--core", type=Path, default=Path("packs/en/core/data.jsonl"))
    parser.add_argument("--oewn-yaml", type=Path, default=Path(".cache/sources/oewn-2025/src/yaml"))
    parser.add_argument("--seed", type=Path, default=Path("packs/en/trans-vi/seed.jsonl"))
    parser.add_argument("--merge-seed", action="store_true")
    args = parser.parse_args()
    load_env(args.env_file)
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY is missing")
    items = build_items(args.registry, args.core, args.oewn_yaml, args.seed, args.output)
    if args.limit > 0:
        items = items[: args.limit]
    groups = [items[index : index + args.group_size] for index in range(0, len(items), args.group_size)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    completed = 0
    attempted = 0
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {pool.submit(request_translation_group, api_key, group): group for group in groups}
        with args.output.open("a", encoding="utf-8") as handle:
            for future in as_completed(futures):
                group = futures[future]
                attempted += len(group)
                try:
                    results = future.result()
                    for result in results:
                        handle.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
                    handle.flush()
                    completed += len(results)
                except Exception as error:
                    failures.append(str(error))
                if attempted % 500 < len(group):
                    print(f"progress {attempted}/{len(items)} ok={completed} failed={attempted - completed}", flush=True)
    print(json.dumps({"requested": len(items), "completed": completed, "failed": failures[:20], "output": args.output.as_posix()}, ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)
    if args.merge_seed:
        merge_seed(args.seed, args.output)
        print(f"merged {args.output} into {args.seed}")


if __name__ == "__main__":
    main()
