#!/usr/bin/env python3
"""Prepare, submit, and safely merge a small OpenAI Batch learning-note expansion."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

try:
    from scripts.batch_trans_vi_luna_meanings import api_request, download_output, load_api_key, multipart_file, refresh_status
    from scripts.merge_en_function_words_core import _refresh_metadata, _write_jsonl_atomically
    from scripts.build_core_en import load_id_registry
except ModuleNotFoundError:
    from batch_trans_vi_luna_meanings import api_request, download_output, load_api_key, multipart_file, refresh_status
    from merge_en_function_words_core import _refresh_metadata, _write_jsonl_atomically
    from build_core_en import load_id_registry


WORD = re.compile(r"[a-z]{4,}")
QUEUE_FIELDS = {"word", "pos"}
RECORD_FIELDS = {"word", "grammar_patterns", "word_family", "usage_notes", "confusables"}
SYSTEM = """You are an English-Vietnamese dictionary editor creating concise learning notes. Return exactly one record for every input word. Give only high-confidence information useful for general learners: grammar patterns, word family, short usage notes, and commonly confused words. A word-family item is only a related different headword; return its English spelling only, with no POS or Vietnamese meaning. Do not include inflections or the input word itself. Do not claim a word is in an exam, do not invent rare senses, and do not add a field outside the schema. Patterns must be compact English templates; Vietnamese must be natural. Leave a list empty when no useful high-confidence item belongs there, but each record needs at least one nonempty learning field."""
SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"records": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "word": {"type": "string"},
            "grammar_patterns": {"type": "array", "maxItems": 3, "items": {"type": "object", "additionalProperties": False, "properties": {"pattern": {"type": "string"}, "vi": {"type": "string"}}, "required": ["pattern", "vi"]}},
            "word_family": {"type": "array", "maxItems": 3, "items": {"type": "object", "additionalProperties": False, "properties": {"word": {"type": "string"}}, "required": ["word"]}},
            "usage_notes": {"type": "array", "maxItems": 1, "items": {"type": "object", "additionalProperties": False, "properties": {"en": {"type": "string"}, "vi": {"type": "string"}}, "required": ["en", "vi"]}},
            "confusables": {"type": "array", "maxItems": 2, "items": {"type": "object", "additionalProperties": False, "properties": {"word": {"type": "string"}, "vi": {"type": "string"}}, "required": ["word", "vi"]}},
        }, "required": sorted(RECORD_FIELDS),
    }}}, "required": ["records"],
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


def build_queue(core_path: Path, limit: int, excluded: set[str] | None = None) -> list[dict[str, Any]]:
    if limit < 1:
        raise ValueError("limit must be positive")
    excluded = excluded or set()
    candidates = []
    for record in read_jsonl(core_path):
        word = record["word"]
        if "learning" in record or not WORD.fullmatch(word.casefold()) or not isinstance(record.get("frequency"), int):
            continue
        pos = sorted({sense["pos"] for sense in record["senses"] if sense["pos"] in {"noun", "verb", "adj", "adv"}})
        if pos:
            candidates.append((record["frequency"], word.casefold(), {"word": word, "pos": pos}))
    candidates.sort()
    output, seen = [], set()
    for _, key, row in candidates:
        if key not in seen and key not in excluded:
            output.append(row); seen.add(key)
        if len(output) == limit:
            break
    return output


def build_requests(rows: list[dict[str, Any]], model: str, group_size: int) -> list[dict[str, Any]]:
    if not 1 <= group_size <= 10:
        raise ValueError("group_size must be between 1 and 10")
    if any(set(row) != QUEUE_FIELDS for row in rows):
        raise ValueError("invalid learning queue")
    requests = []
    for offset in range(0, len(rows), group_size):
        group = rows[offset:offset + group_size]
        requests.append({
            "custom_id": f"learning-vi-{len(requests) + 1:04d}", "method": "POST", "url": "/v1/responses",
            "body": {"model": model, "input": [
                {"role": "system", "content": [{"type": "input_text", "text": SYSTEM}]},
                {"role": "user", "content": [{"type": "input_text", "text": "Return learning records for this JSON input:\n" + json.dumps(group, ensure_ascii=False, separators=(",", ":"))}]},
            ], "text": {"format": {"type": "json_schema", "name": "learning_vi_records", "strict": True, "schema": SCHEMA}, "verbosity": "low"}, "reasoning": {"effort": "none"}},
        })
    return requests


def validate_record(row: Any, words: set[str]) -> str | None:
    if not isinstance(row, dict) or set(row) != RECORD_FIELDS or not isinstance(row.get("word"), str) or row["word"].casefold() not in words:
        return "invalid or unknown word"
    for field, keys in (("grammar_patterns", {"pattern", "vi"}), ("usage_notes", {"en", "vi"}), ("confusables", {"word", "vi"})):
        if not isinstance(row[field], list) or any(not isinstance(item, dict) or set(item) != keys or not all(isinstance(value, str) and value.strip() for value in item.values()) for item in row[field]):
            return f"invalid {field}"
    # Accept the previous Batch shape too, so an already-submitted batch is usable.
    if not isinstance(row["word_family"], list) or any(not isinstance(item, dict) or set(item) not in ({"word"}, {"word", "pos", "meaning"}) or not isinstance(item.get("word"), str) or not item["word"].strip() for item in row["word_family"]):
        return "invalid word_family"
    if not any(row[field] for field in RECORD_FIELDS - {"word"}):
        return "empty learning record"
    return None


def clean_record(row: Any) -> Any:
    if not isinstance(row, dict):
        return row
    cleaned = dict(row)
    for field, keys in (("grammar_patterns", {"pattern", "vi"}), ("usage_notes", {"en", "vi"}), ("confusables", {"word", "vi"})):
        if isinstance(cleaned.get(field), list):
            cleaned[field] = [item for item in cleaned[field] if isinstance(item, dict) and set(item) == keys and all(isinstance(value, str) and value.strip() for value in item.values())]
    if isinstance(cleaned.get("word_family"), list):
        cleaned["word_family"] = [item for item in cleaned["word_family"] if isinstance(item, dict) and set(item) in ({"word"}, {"word", "pos", "meaning"}) and isinstance(item.get("word"), str) and item["word"].strip()]
    return cleaned


def normalize_learning(row: dict[str, Any], headwords: dict[str, str]) -> dict[str, Any] | None:
    """Keep only distinct, resolvable related headwords; never duplicate the open record."""
    key = row["word"].casefold()
    family, seen = [], set()
    for item in row["word_family"]:
        target = item["word"].strip().casefold()
        if target != key and target in headwords and target not in seen:
            family.append({"word": headwords[target]})
            seen.add(target)
    value = {field: row[field] for field in RECORD_FIELDS - {"word", "word_family"}}
    value["word_family"] = family
    return value if any(value.values()) else None


def _output_text(body: dict[str, Any]) -> str | None:
    if isinstance(body.get("output_text"), str):
        return body["output_text"]
    for item in body.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    return None


def parse_output(path: Path, queue: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    words = {row["word"].casefold() for row in queue}
    accepted, errors = {}, []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            response = json.loads(line)["response"]
            if int(response["status_code"]) != 200:
                raise ValueError(f"HTTP {response['status_code']}")
            records = json.loads(_output_text(response["body"]) or "")["records"]
            if not isinstance(records, list):
                raise ValueError("records is not a list")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"line {number}: invalid Batch response ({error})")
            continue
        for row in records:
            error = validate_record(row, words)
            key = row.get("word", "").casefold() if isinstance(row, dict) else ""
            if error:
                errors.append(f"line {number}: {error}")
            elif key in accepted:
                errors.append(f"line {number}: duplicate word {key}")
            else:
                accepted[key] = row
    errors.extend(f"missing word {word}" for word in sorted(words - set(accepted)))
    return [accepted[word] for word in sorted(accepted)], errors


def salvage_output(path: Path, queue: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit < 1:
        raise ValueError("limit must be positive")
    words = {row["word"].casefold() for row in queue}
    recovered: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            response = json.loads(line)["response"]
            records = json.loads(_output_text(response["body"]) or "")["records"] if int(response["status_code"]) == 200 else []
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        for row in records:
            key = row.get("word", "").casefold() if isinstance(row, dict) else ""
            cleaned = clean_record(row)
            if key not in recovered and validate_record(row, words) is not None and validate_record(cleaned, words) is None:
                recovered[key] = cleaned
    return [recovered[row["word"].casefold()] for row in queue if row["word"].casefold() in recovered][:limit]


def submit_batch(input_path: Path, metadata_path: Path, env_path: Path) -> dict[str, Any]:
    key = load_api_key(env_path)
    body, content_type = multipart_file(input_path)
    file_result = json.loads(api_request("/files", "POST", key, body, content_type))
    batch = json.loads(api_request("/batches", "POST", key, json.dumps({"input_file_id": file_result["id"], "endpoint": "/v1/responses", "completion_window": "24h", "metadata": {"pipeline": "learning-vi"}}, separators=(",", ":")).encode(), "application/json"))
    metadata = {"batch_id": batch["id"], "input_file_id": file_result["id"], "status": batch["status"], "request_count": len(read_jsonl(input_path))}
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def apply_records(accepted_path: Path, core_path: Path, registry_path: Path, core_meta_path: Path) -> int:
    records = read_jsonl(core_path)
    accepted = read_jsonl(accepted_path)
    headwords = {record["word"].casefold(): record["word"] for record in records}
    words = set(headwords)
    if any(validate_record(row, words) for row in accepted):
        raise ValueError("accepted file contains invalid records")
    learning = {row["word"].casefold(): value for row in accepted if (value := normalize_learning(row, headwords))}
    for record in records:
        if value := learning.get(record["word"].casefold()):
            record["learning"] = value
    _write_jsonl_atomically(core_path, records)
    _refresh_metadata(core_meta_path, core_path, records, load_id_registry(registry_path))
    return len(accepted)


def normalize_core(core_path: Path, registry_path: Path, core_meta_path: Path) -> int:
    records = read_jsonl(core_path)
    headwords = {record["word"].casefold(): record["word"] for record in records}
    changed = 0
    for record in records:
        learning = record.get("learning")
        if not isinstance(learning, dict):
            continue
        row = {"word": record["word"], **learning}
        value = normalize_learning(row, headwords)
        if value:
            if value != learning:
                record["learning"] = value
                changed += 1
        else:
            record.pop("learning")
            changed += 1
    _write_jsonl_atomically(core_path, records)
    _refresh_metadata(core_meta_path, core_path, records, load_id_registry(registry_path))
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    queue = commands.add_parser("queue"); queue.add_argument("--core", type=Path, default=Path("packs/en/core/data.jsonl")); queue.add_argument("--output", type=Path, required=True); queue.add_argument("--limit", type=int, default=500); queue.add_argument("--exclude", type=Path, action="append", default=[])
    prepare = commands.add_parser("prepare"); prepare.add_argument("--queue", type=Path, required=True); prepare.add_argument("--output", type=Path, required=True); prepare.add_argument("--model", default="gpt-5.6-luna"); prepare.add_argument("--group-size", type=int, default=10)
    submit = commands.add_parser("submit"); submit.add_argument("--input", type=Path, required=True); submit.add_argument("--metadata", type=Path, required=True); submit.add_argument("--env", type=Path, default=Path(".env"))
    status = commands.add_parser("status"); status.add_argument("--metadata", type=Path, required=True); status.add_argument("--env", type=Path, default=Path(".env"))
    download = commands.add_parser("download"); download.add_argument("--metadata", type=Path, required=True); download.add_argument("--output", type=Path, required=True); download.add_argument("--env", type=Path, default=Path(".env"))
    parse = commands.add_parser("parse"); parse.add_argument("--batch", type=Path, required=True); parse.add_argument("--queue", type=Path, required=True); parse.add_argument("--output", type=Path, required=True); parse.add_argument("--retry", type=Path, required=True)
    salvage = commands.add_parser("salvage"); salvage.add_argument("--batch", type=Path, required=True); salvage.add_argument("--queue", type=Path, required=True); salvage.add_argument("--output", type=Path, required=True); salvage.add_argument("--limit", type=int, required=True)
    apply = commands.add_parser("apply"); apply.add_argument("--accepted", type=Path, required=True); apply.add_argument("--core", type=Path, default=Path("packs/en/core/data.jsonl")); apply.add_argument("--registry", type=Path, default=Path("packs/en/core/sense-ids.tsv")); apply.add_argument("--core-meta", type=Path, default=Path("packs/en/core/meta.json"))
    normalize = commands.add_parser("normalize"); normalize.add_argument("--core", type=Path, default=Path("packs/en/core/data.jsonl")); normalize.add_argument("--registry", type=Path, default=Path("packs/en/core/sense-ids.tsv")); normalize.add_argument("--core-meta", type=Path, default=Path("packs/en/core/meta.json"))
    args = parser.parse_args(argv)
    if args.command == "queue":
        excluded = {row["word"].casefold() for path in args.exclude for row in read_jsonl(path) if isinstance(row.get("word"), str)}
        rows = build_queue(args.core, args.limit, excluded); write_jsonl(args.output, rows); return len(rows)
    if args.command == "prepare":
        rows = build_requests(read_jsonl(args.queue), args.model, args.group_size); write_jsonl(args.output, rows); return len(rows)
    if args.command == "submit": print(json.dumps(submit_batch(args.input, args.metadata, args.env))); return 0
    if args.command == "status": print(json.dumps(refresh_status(args.metadata, args.env))); return 0
    if args.command == "download": print(download_output(args.metadata, args.output, args.env)); return 0
    if args.command == "parse":
        queue_rows = read_jsonl(args.queue); rows, errors = parse_output(args.batch, queue_rows); write_jsonl(args.output, rows); write_jsonl(args.retry, [row for row in queue_rows if row["word"].casefold() not in {item["word"].casefold() for item in rows}]);
        if errors: raise ValueError("; ".join(errors[:20]))
        return len(rows)
    if args.command == "salvage":
        rows = salvage_output(args.batch, read_jsonl(args.queue), args.limit); write_jsonl(args.output, rows); return len(rows)
    if args.command == "normalize": return normalize_core(args.core, args.registry, args.core_meta)
    return apply_records(args.accepted, args.core, args.registry, args.core_meta)


if __name__ == "__main__":
    raise SystemExit(main())
