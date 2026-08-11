#!/usr/bin/env python3
"""Build and validate strict rich Luna Batch requests for function words."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

try:
    from scripts.batch_trans_vi_luna_meanings import (
        api_json, api_request, load_api_key, multipart_file, read_jsonl, write_jsonl,
    )
except ModuleNotFoundError:  # direct script execution
    from batch_trans_vi_luna_meanings import (
        api_json, api_request, load_api_key, multipart_file, read_jsonl, write_jsonl,
    )


QUEUE_FIELDS = {
    "source_key", "word", "pos", "category", "priority", "description_hint", "usage_hint", "sense_id"
}
RICH_FIELDS = {"sense_id", "meaning", "description", "examples", "collocations"}
MEANING_SEPARATORS = set(" ,;/-")
ASCII_WORD_RE = re.compile(r"[a-z]+(?:'[a-z]+)?")
GRAMMAR_WORDS = {
    "adjective", "adverb", "adverbial", "article", "auxiliary", "clause", "conjunction",
    "contraction", "determiner", "form", "interrogative", "modal", "negator", "noun",
    "object", "particle", "possessive", "preposition", "pronoun", "quantifier", "relative",
    "subject", "verb",
}
CATEGORY_DESCRIPTION_TERMS = {
    "pronoun": {"pronoun"}, "article": {"article"}, "determiner": {"determiner"},
    "quantifier": {"quantifier"}, "distributive": {"distributive", "determiner"},
    "preposition": {"preposition"}, "conjunction": {"conjunction"}, "auxiliary": {"auxiliary"},
    "modal": {"modal"}, "negator": {"negator", "negative"}, "particle": {"particle"},
    "discourse_adverb": {"adverb", "discourse"}, "contraction": {"contraction"},
}
SYSTEM_PROMPT = """You are a careful English-to-Vietnamese dictionary editor for English function words.
For every supplied form, return exactly one rich record. Meaning must be a concise natural Vietnamese headword or phrase. Description must be a capitalized, punctuated English grammatical explanation specific to the form and name its category. Examples must contain exactly one natural nonempty bilingual object with en and vi. Collocations must contain one to three natural English phrases; each must include the input word exactly plus real surrounding context. Preserve sense_id exactly. Do not add fields."""
RESPONSE_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "properties": {"translations": {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "properties": {
            "sense_id": {"type": "integer"}, "meaning": {"type": "string"},
            "description": {"type": "string"},
            "examples": {"type": "array", "minItems": 1, "maxItems": 1, "items": {
                "type": "object", "additionalProperties": False,
                "properties": {"en": {"type": "string"}, "vi": {"type": "string"}},
                "required": ["en", "vi"],
            }},
            "collocations": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "string"}},
        }, "required": ["sense_id", "meaning", "description", "examples", "collocations"],
    }}}, "required": ["translations"],
}


def build_requests(rows: list[dict[str, Any]], model: str, group_size: int) -> list[dict[str, Any]]:
    if not 1 <= group_size <= 25:
        raise ValueError("group_size must be between 1 and 25")
    requests = []
    for offset in range(0, len(rows), group_size):
        group = rows[offset : offset + group_size]
        for row in group:
            if set(row) != QUEUE_FIELDS:
                raise ValueError(f"invalid queue fields for {row.get('sense_id')}")
        requests.append({
            "custom_id": f"function-word-{len(requests) + 1:06d}", "method": "POST", "url": "/v1/responses",
            "body": {"model": model, "input": [
                {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]},
                {"role": "user", "content": [{"type": "input_text", "text": "Return rich records for every input row. Input JSON:\n" + json.dumps(group, ensure_ascii=False, separators=(",", ":"))}]},
            ], "text": {"format": {"type": "json_schema", "name": "function_word_rich_translations", "strict": True, "schema": RESPONSE_SCHEMA}, "verbosity": "low"}, "reasoning": {"effort": "low"}},
        })
    return requests


def schema_required_fields(request: dict[str, Any]) -> list[str]:
    return request["body"]["text"]["format"]["schema"]["properties"]["translations"]["items"]["required"]


def _has_non_garbage_context(tokens: list[str]) -> bool:
    letters = [token.replace("'", "") for token in tokens]
    return bool(letters) and not any(
        len(token) > 1 and len(set(token)) == 1 for token in letters
    )


def validate_rich_row(row: Any, source: dict[str, Any] | None = None) -> str | None:
    if not isinstance(row, dict) or set(row) != RICH_FIELDS:
        return "invalid rich row fields"
    if not isinstance(row["sense_id"], int) or isinstance(row["sense_id"], bool):
        return "invalid sense_id"
    if not isinstance(row["meaning"], str) or not row["meaning"].strip():
        return "empty meaning"
    meaning = unicodedata.normalize("NFC", row["meaning"].strip()).casefold()
    words = re.findall(r"[^\W\d_]+", meaning)
    if (
        len(meaning) > 50 or not 1 <= len(words) <= 12
        or meaning[-1] in ".!?"
        or any((not char.isalpha() or "LATIN" not in unicodedata.name(char, "")) and char not in MEANING_SEPARATORS for char in meaning)
        or any(not set(unicodedata.normalize("NFD", word)) & set("aeiouy") for word in words)
    ):
        return "meaning must be concise Vietnamese headword"
    description = row["description"]
    description_words = ASCII_WORD_RE.findall(description.casefold()) if isinstance(description, str) else []
    if not isinstance(description, str) or not description.strip() or not description[0].isupper() or description[-1] not in ".!?":
        return "description must be capitalized English sentence"
    if not description.isascii() or len(description_words) < 3 or not any(word.strip(".,;:()'") in GRAMMAR_WORDS for word in description_words):
        return "description must be English grammatical explanation"
    if source is not None:
        category = source.get("category")
        if category not in CATEGORY_DESCRIPTION_TERMS or not any(word.strip(".,;:()'") in CATEGORY_DESCRIPTION_TERMS[category] for word in description_words):
            return "description must match source grammatical category"
        if len(description_words) < 4:
            return "description must be sufficiently explanatory"
    examples = row["examples"]
    if not isinstance(examples, list) or len(examples) != 1 or not isinstance(examples[0], dict) or set(examples[0]) != {"en", "vi"} or not all(isinstance(examples[0][key], str) and examples[0][key].strip() for key in ("en", "vi")):
        return "expected one bilingual example"
    collocations = row["collocations"]
    if not isinstance(collocations, list) or not 1 <= len(collocations) <= 3 or not all(isinstance(value, str) and value.strip() for value in collocations):
        return "expected one to three collocations"
    if not all(value.isascii() and len(ASCII_WORD_RE.findall(value.casefold())) >= 2 for value in collocations):
        return "collocations must be natural phrases"
    if source is not None:
        form = str(source.get("word", "")).casefold().replace("’", "'")
        matches = [re.search(rf"(?<![a-z]){re.escape(form)}(?![a-z])", value.casefold().replace("’", "'")) for value in collocations]
        if not form or any(match is None for match in matches):
            return "collocations must include source form"
        for value, match in zip(collocations, matches):
            assert match is not None
            context = ASCII_WORD_RE.findall((value[:match.start()] + " " + value[match.end():]).casefold())
            if not _has_non_garbage_context(context):
                return "collocations must include usable context"
    if any(
        len(value.strip()) < 3
        or not _has_non_garbage_context(ASCII_WORD_RE.findall(value.casefold()))
        for value in collocations
    ):
        return "collocations must be natural phrases"
    return None


def _output_text(body: dict[str, Any]) -> str | None:
    if isinstance(body.get("output_text"), str):
        return body["output_text"]
    for item in body.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    return None


def parse_output(path: Path, expected_rows: dict[int, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    expected_ids = set(expected_rows)
    accepted, errors = {}, []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            result = json.loads(line); custom_id = str(result["custom_id"]); response = result["response"]
            if int(response["status_code"]) != 200:
                raise ValueError(f"HTTP {response['status_code']}")
            translations = json.loads(_output_text(response["body"]) or "")["translations"]
            if not isinstance(translations, list):
                raise ValueError("translations is not an array")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"line {number}: invalid Batch response ({error})"); continue
        group = {}
        for row in translations:
            sense_id = row.get("sense_id") if isinstance(row, dict) else None
            if not isinstance(sense_id, int) or isinstance(sense_id, bool):
                errors.append(f"{custom_id}: invalid sense_id {sense_id}"); continue
            if sense_id not in expected_ids:
                errors.append(f"{custom_id}: unknown sense_id {sense_id}"); continue
            if sense_id in accepted or sense_id in group:
                errors.append(f"{custom_id}: duplicate sense_id {sense_id}"); continue
            if error := validate_rich_row(row, expected_rows[sense_id]):
                errors.append(f"{custom_id}: {error} for sense_id {sense_id}"); continue
            group[sense_id] = row
        accepted.update(group)
    errors.extend(f"missing sense_id {sense_id}" for sense_id in sorted(expected_ids - set(accepted)))
    return [accepted[sense_id] for sense_id in sorted(accepted)], errors


def build_retry_queue(source_paths: list[Path], accepted_paths: list[Path] | None = None) -> list[dict[str, Any]]:
    source, source_by_id = [], {}
    for path in source_paths:
        for row in read_jsonl(path):
            if set(row) != QUEUE_FIELDS:
                raise ValueError(f"{path}: expected function-word queue fields")
            sense_id = row["sense_id"]
            if sense_id in source_by_id:
                raise ValueError(f"duplicate source sense_id {sense_id}")
            source.append(row); source_by_id[sense_id] = row
    recovered = set()
    for path in accepted_paths or []:
        for row in read_jsonl(path):
            if row["sense_id"] not in source_by_id:
                raise ValueError(f"{path}: recovered unknown sense_id {row['sense_id']}")
            if validate_rich_row(row, source_by_id[row["sense_id"]]):
                raise ValueError(f"{path}: expected rich accepted fields")
            recovered.add(row["sense_id"])
    return [row for row in source if row["sense_id"] not in recovered]


def submit_batch(input_path: Path, metadata_path: Path, env_path: Path) -> dict[str, Any]:
    key = load_api_key(env_path); body, content_type = multipart_file(input_path)
    file_result = json.loads(api_request("/files", "POST", key, body, content_type))
    batch = api_json("/batches", "POST", key, {"input_file_id": file_result["id"], "endpoint": "/v1/responses", "completion_window": "24h", "metadata": {"pipeline": "trans-vi-function-words"}})
    metadata = {"batch_id": batch["id"], "input_file_id": file_result["id"], "status": batch["status"], "request_count": len(read_jsonl(input_path))}
    metadata_path.parent.mkdir(parents=True, exist_ok=True); metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def refresh_status(metadata_path: Path, env_path: Path) -> dict[str, Any]:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")); result = api_json(f"/batches/{metadata['batch_id']}", "GET", load_api_key(env_path))
    metadata.update({"status": result["status"], "output_file_id": result.get("output_file_id"), "error_file_id": result.get("error_file_id"), "request_counts": result.get("request_counts")})
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8"); return metadata


def download_output(metadata_path: Path, output_path: Path, env_path: Path) -> int:
    metadata = refresh_status(metadata_path, env_path)
    if metadata.get("status") not in {"completed", "cancelled"} or not metadata.get("output_file_id"):
        raise RuntimeError(f"Batch is {metadata['status']}; output is not ready")
    payload = api_request(f"/files/{metadata['output_file_id']}/content", "GET", load_api_key(env_path))
    output_path.parent.mkdir(parents=True, exist_ok=True); output_path.write_bytes(payload); return len(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__); commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare"); prepare.add_argument("--queue", type=Path, required=True); prepare.add_argument("--output", type=Path, required=True); prepare.add_argument("--limit", type=int); prepare.add_argument("--offset", type=int, default=0); prepare.add_argument("--group-size", type=int, default=25); prepare.add_argument("--model", default="gpt-5.6-luna")
    for name in ("submit", "status", "download"):
        command = commands.add_parser(name); command.add_argument("--metadata", type=Path, required=True); command.add_argument("--env", type=Path, default=Path(".env"))
        if name == "submit": command.add_argument("--input", type=Path, required=True)
        if name == "download": command.add_argument("--output", type=Path, required=True)
    parse = commands.add_parser("parse"); parse.add_argument("--batch", type=Path, required=True); parse.add_argument("--queue", type=Path, required=True); parse.add_argument("--output", type=Path, required=True); parse.add_argument("--limit", type=int); parse.add_argument("--offset", type=int, default=0); parse.add_argument("--allow-partial", action="store_true"); parse.add_argument("--retry-queue", type=Path)
    retry = commands.add_parser("retry-queue"); retry.add_argument("--source", action="append", type=Path, required=True); retry.add_argument("--accepted", action="append", type=Path); retry.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        rows = build_requests(read_jsonl(args.queue, args.limit, args.offset), args.model, args.group_size); write_jsonl(args.output, rows); return len(rows)
    if args.command == "submit": print(json.dumps(submit_batch(args.input, args.metadata, args.env), ensure_ascii=False)); return 0
    if args.command == "status": print(json.dumps(refresh_status(args.metadata, args.env), ensure_ascii=False)); return 0
    if args.command == "download": print(download_output(args.metadata, args.output, args.env)); return 0
    if args.command == "parse":
        source = read_jsonl(args.queue, args.limit, args.offset); rows, errors = parse_output(args.batch, {row["sense_id"]: row for row in source})
        if errors and not args.allow_partial: raise ValueError("; ".join(errors[:20]))
        if errors and args.retry_queue is None: raise ValueError("--retry-queue is required with --allow-partial")
        write_jsonl(args.output, rows)
        if errors: write_jsonl(args.retry_queue, [row for row in source if row["sense_id"] not in {row["sense_id"] for row in rows}])
        return len(rows)
    rows = build_retry_queue(args.source, args.accepted); write_jsonl(args.output, rows); return len(rows)


if __name__ == "__main__":
    print(main())
