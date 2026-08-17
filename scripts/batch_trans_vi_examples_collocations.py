#!/usr/bin/env python3
"""Fill missing bilingual examples and collocations with an OpenAI Batch."""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

try:
    from scripts.batch_trans_vi_luna_descriptions import (
        _output_text, download_output, read_jsonl, refresh_status, shard_input,
        submit_batch, write_jsonl,
    )
    from scripts.build_trans_vi_canonical import build_canonical
except ModuleNotFoundError:  # direct script execution
    from batch_trans_vi_luna_descriptions import (
        _output_text, download_output, read_jsonl, refresh_status, shard_input,
        submit_batch, write_jsonl,
    )
    from build_trans_vi_canonical import build_canonical


QUEUE_FIELDS = {"sense_id", "word", "pos", "meaning", "description"}
RICH_FIELDS = {"sense_id", "examples", "collocations"}
PREFIX = "Return one record for every input row. Input JSON:\n"
SYSTEM_PROMPT = """You are a careful English-to-Vietnamese dictionary editor.
For every supplied sense, return exactly one short, natural bilingual example
and exactly one useful English collocation. Use word, part of speech, Vietnamese
meaning, and description to preserve the intended sense. Copy the supplied
word verbatim into the collocation, including every word of a multiword form.
The English example
must be a complete sentence of at most twelve words; its Vietnamese translation
must be natural, fully translated Vietnamese with sentence punctuation. The
English example must use the supplied word, or its ordinary inflected form, in
the intended sense. The collocation must be a two-to-five-word English phrase
containing the supplied word with natural context. Never use part-of-speech
labels, placeholders, question marks, underscores, or editorial commentary in
a collocation. Do not add definitions, commentary, extra examples, translations
outside the example, or extra fields."""
RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "records": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "sense_id": {"type": "integer"},
                    "examples": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 1,
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {"en": {"type": "string"}, "vi": {"type": "string"}},
                            "required": ["en", "vi"],
                        },
                    },
                    "collocations": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 1,
                        "items": {"type": "string"},
                    },
                },
                "required": ["sense_id", "examples", "collocations"],
            },
        },
    },
    "required": ["records"],
}
WORD_RE = re.compile(r"(?:[A-Za-z]+(?:'[A-Za-z]+)?|\d+(?:\.\d+)?)")
GRAMMAR_WORDS = {"adj", "adjective", "adv", "adverb", "noun", "verb"}
LINGUISTIC_RE = re.compile(r"(?i)\b(?:grammar|grammatical|linguistic|language|word|verb|noun|adjective|adverb|tense|case|phrase|clause|pronunciation|orthograph)\w*\b")


def build_queue(core_path: Path, data_path: Path, include_invalid: bool = False) -> list[dict[str, Any]]:
    """Return empty rich fields, plus populated invalid fields when requested."""
    core = {
        sense["id"]: {"word": word["word"], "pos": sense["pos"]}
        for word in read_jsonl(core_path)
        for sense in word["senses"]
    }
    data = {row["sense_id"]: row for row in read_jsonl(data_path)}
    if set(core) != set(data):
        raise ValueError("core and translation sense IDs differ")
    queue = []
    for sense_id in sorted(core):
        row = data[sense_id]
        examples, collocations = row["examples"], row["collocations"]
        if bool(examples) != bool(collocations):
            raise ValueError(f"partially populated rich fields for sense_id {sense_id}")
        if not row["meaning"].strip() or not row["description"].strip():
            raise ValueError(f"missing dictionary context for sense_id {sense_id}")
        source = {"sense_id": sense_id, **core[sense_id], "meaning": row["meaning"], "description": row["description"]}
        rich = {"sense_id": sense_id, "examples": examples, "collocations": collocations}
        if not examples or include_invalid and validate_rich_fields(rich, source):
            queue.append(source)
    return queue


def build_requests(
    rows: list[dict[str, Any]],
    model: str,
    group_size: int,
    reasoning_effort: str | None = None,
) -> list[dict[str, Any]]:
    if not 1 <= group_size <= 25:
        raise ValueError("group_size must be between 1 and 25")
    requests = []
    for offset in range(0, len(rows), group_size):
        group = rows[offset : offset + group_size]
        if any(set(row) != QUEUE_FIELDS for row in group):
            raise ValueError("invalid rich-fields queue fields")
        requests.append({
            "custom_id": f"rich-fields-{len(requests) + 1:06d}",
            "method": "POST",
            "url": "/v1/responses",
            "body": {
                "model": model,
                "input": [
                    {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]},
                    {"role": "user", "content": [{"type": "input_text", "text": PREFIX + json.dumps(group, ensure_ascii=False, separators=(",", ":"))}]},
                ],
                "text": {"format": {"type": "json_schema", "name": "dictionary_rich_fields", "strict": True, "schema": RESPONSE_SCHEMA}, "verbosity": "low"},
                "reasoning": {"effort": reasoning_effort or ("none" if model.startswith("gpt-5.6-") else "minimal")},
                "max_output_tokens": max(400, group_size * 120),
            },
        })
    return requests


def rows_from_batch_input(path: Path) -> list[dict[str, Any]]:
    rows = []
    for number, request in enumerate(read_jsonl(path), 1):
        try:
            text = request["body"]["input"][1]["content"][0]["text"]
            group = json.loads(text.removeprefix(PREFIX))
        except (AttributeError, IndexError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError(f"input line {number}: invalid rich-fields Batch request") from error
        if not text.startswith(PREFIX) or not isinstance(group, list) or any(set(row) != QUEUE_FIELDS for row in group):
            raise ValueError(f"input line {number}: invalid rich-fields Batch request")
        rows.extend(group)
    if len({row["sense_id"] for row in rows}) != len(rows):
        raise ValueError("rich-fields Batch input has duplicate sense IDs")
    return rows


def validate_rich_fields(row: Any, source: dict[str, Any] | None = None) -> str | None:
    if not isinstance(row, dict) or set(row) != RICH_FIELDS:
        return "invalid rich-fields record"
    if not isinstance(row["sense_id"], int) or isinstance(row["sense_id"], bool):
        return "invalid sense_id"
    examples = row["examples"]
    if not isinstance(examples, list) or len(examples) != 1 or not isinstance(examples[0], dict) or set(examples[0]) != {"en", "vi"}:
        return "expected one bilingual example"
    english, vietnamese = examples[0].get("en"), examples[0].get("vi")
    if not isinstance(english, str) or not english.strip() or len(english.strip()) > 160 or not re.search(r"[.!?][\"'’”]?\Z", english.strip()):
        return "invalid English example"
    if not isinstance(vietnamese, str) or not vietnamese.strip() or len(vietnamese.strip()) > 200 or not re.search(r"[.!?][\"'’”]?\Z", vietnamese.strip()):
        return "invalid Vietnamese example"
    english, vietnamese = (unicodedata.normalize("NFC", value.strip()) for value in (english, vietnamese))
    if english.casefold() == vietnamese.casefold():
        return "Vietnamese example duplicates English"
    vietnamese_words = re.findall(r"[A-Za-zÀ-ỹĐđ]+", vietnamese)
    if len(vietnamese_words) >= 4 and vietnamese.isascii():
        return "Vietnamese example is untranslated ASCII"
    if any("\u4e00" <= char <= "\u9fff" or char == "�" for char in vietnamese):
        return "invalid characters in Vietnamese example"
    if re.search(r"(?i)\b(?:vwidth|not appropriate)\b", vietnamese):
        return "model artifact in Vietnamese example"
    collocations = row["collocations"]
    if not isinstance(collocations, list) or not 1 <= len(collocations) <= 3 or not all(isinstance(value, str) for value in collocations):
        return "expected one to three collocations"
    form = str(source["word"]).casefold().replace("’", "'") if source is not None else ""
    form_word_list = [value.casefold() for value in WORD_RE.findall(form)]
    form_words = set(form_word_list)
    linguistic = bool(source is not None and LINGUISTIC_RE.search(str(source.get("description", ""))))
    for value in collocations:
        collocation = unicodedata.normalize("NFC", value.strip())
        words = [word.casefold() for word in WORD_RE.findall(collocation)]
        if (len(collocation) > 160 or not 2 <= len(words) <= max(5, len(form_word_list) + 2)
                or any(char in collocation for char in "?_:;()[]{}")
                or "/" in collocation and "/" not in form):
            return "invalid collocation"
        normalized = collocation.casefold().replace("’", "'")
        definition_marker = re.search(
            r"(?i)\b(?:its sense|indicates|is used as|is a|relating to|shows up in)\b", collocation
        ) or "means" not in form_words and re.search(r"(?i)\bmeans\b", collocation)
        if definition_marker:
            return "definition or translation in collocation"
        description = str(source.get("description", "")).strip().rstrip(".").casefold() if source else ""
        if description and len(WORD_RE.findall(description)) >= 3 and normalized == f"{form} {description}":
            return "description pasted into collocation"
        if (not linguistic and source is not None and source.get("pos") != "adj"
                and len(words) > len(form_word_list) and words[len(form_word_list)] in GRAMMAR_WORDS
                and words[:len(form_word_list)] == form_word_list):
            return "part-of-speech label in collocation"
        if source is not None and re.fullmatch(r"[a-z]+(?:[ '’-][a-z]+)*", form):
            contains_form = bool(re.search(rf"(?<![a-z]){re.escape(form)}(?![a-z])", normalized))
            if not contains_form and len(form_words) == 1:
                inflections = {f"{form}s", f"{form}es"}
                if form.endswith("y"):
                    inflections.add(f"{form[:-1]}ies")
                contains_form = any(word in inflections for word in words)
            if not contains_form:
                return "collocation must include source form"
    return None


def parse_output(path: Path, expected_rows: dict[int, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    accepted, errors = {}, []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            result = json.loads(line)
            response = result["response"]
            if int(response["status_code"]) != 200:
                raise ValueError(f"HTTP {response['status_code']}")
            records = json.loads(_output_text(response["body"]) or "")["records"]
            if not isinstance(records, list):
                raise ValueError("records is not an array")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"line {number}: invalid Batch response ({error})")
            continue
        for row in records:
            sense_id = row.get("sense_id") if isinstance(row, dict) else None
            if not isinstance(sense_id, int) or sense_id not in expected_rows:
                errors.append(f"line {number}: unknown sense_id {sense_id}")
            elif sense_id in accepted:
                errors.append(f"line {number}: duplicate sense_id {sense_id}")
            elif error := validate_rich_fields(row, expected_rows[sense_id]):
                errors.append(f"line {number}: {error} for sense_id {sense_id}")
            else:
                accepted[sense_id] = {
                    "sense_id": sense_id,
                    "examples": [{key: unicodedata.normalize("NFC", row["examples"][0][key].strip()) for key in ("en", "vi")}],
                    "collocations": [unicodedata.normalize("NFC", row["collocations"][0].strip())],
                }
    errors.extend(f"missing sense_id {sense_id}" for sense_id in sorted(set(expected_rows) - set(accepted)))
    return [accepted[sense_id] for sense_id in sorted(accepted)], errors


def fallback_rows(batch_path: Path, expected_rows: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    """Recover only complete model rows that pass the normal quality gate."""
    recovered: dict[int, dict[str, Any]] = {}
    for line in batch_path.read_text(encoding="utf-8").splitlines():
        try:
            records = json.loads(_output_text(json.loads(line)["response"]["body"]) or "")["records"]
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        for row in records:
            sense_id = row.get("sense_id") if isinstance(row, dict) else None
            if sense_id in expected_rows and sense_id not in recovered and validate_rich_fields(row, expected_rows[sense_id]) is None:
                recovered[sense_id] = row
    return [recovered[sense_id] for sense_id in sorted(recovered)]


def apply_fields(data_path: Path, accepted_paths: list[Path], queue_path: Path, allow_partial: bool = False, replace_invalid: bool = False) -> int:
    queue = read_jsonl(queue_path)
    source = queue if all("sense_id" in row for row in queue) else rows_from_batch_input(queue_path)
    expected_rows = {row["sense_id"]: row for row in source}
    accepted = {}
    for path in accepted_paths:
        for row in read_jsonl(path):
            sense_id = row.get("sense_id") if isinstance(row, dict) else None
            if sense_id in accepted:
                raise ValueError(f"duplicate accepted sense_id {sense_id}")
            accepted[sense_id] = row
    if (not accepted or not set(accepted) <= set(expected_rows) or (not allow_partial and set(accepted) != set(expected_rows))
            or any(validate_rich_fields(row, expected_rows.get(row["sense_id"])) for row in accepted.values())):
        raise ValueError("accepted rich fields do not cover the queue safely")
    records = read_jsonl(data_path)
    for row in records:
        if row["sense_id"] in accepted:
            current = {"sense_id": row["sense_id"], "examples": row["examples"], "collocations": row["collocations"]}
            source_row = expected_rows[row["sense_id"]]
            if (row["examples"] or row["collocations"]) and not replace_invalid:
                raise ValueError(f"rich fields are no longer empty for sense_id {row['sense_id']}")
            if replace_invalid and row["examples"] and validate_rich_fields(current, source_row) is None:
                raise ValueError(f"refusing to replace valid rich fields for sense_id {row['sense_id']}")
            row.update(accepted[row["sense_id"]])
    write_jsonl(data_path.with_suffix(data_path.suffix + ".tmp"), records)
    data_path.with_suffix(data_path.suffix + ".tmp").replace(data_path)
    return len(accepted)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    queue = commands.add_parser("queue")
    queue.add_argument("--core", type=Path, default=Path("packs/en/core/data.jsonl"))
    queue.add_argument("--data", type=Path, default=Path("packs/en/trans-vi/data.jsonl"))
    queue.add_argument("--output", type=Path, required=True)
    queue.add_argument("--include-invalid", action="store_true")
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--queue", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--group-size", type=int, default=5)
    prepare.add_argument("--model", default="gpt-5-nano")
    prepare.add_argument("--reasoning-effort")
    shard = commands.add_parser("shard")
    shard.add_argument("--input", type=Path, required=True)
    shard.add_argument("--output-dir", type=Path, required=True)
    shard.add_argument("--max-bytes", type=int, required=True)
    for name in ("submit", "status", "download"):
        command = commands.add_parser(name)
        command.add_argument("--metadata", type=Path, required=True)
        command.add_argument("--env", type=Path, default=Path(".env"))
        if name == "submit":
            command.add_argument("--input", type=Path, required=True)
        if name == "download":
            command.add_argument("--output", type=Path, required=True)
    parse = commands.add_parser("parse")
    parse.add_argument("--batch", type=Path, required=True)
    parse.add_argument("--queue", type=Path)
    parse.add_argument("--input", type=Path)
    parse.add_argument("--output", type=Path, required=True)
    parse.add_argument("--allow-partial", action="store_true")
    parse.add_argument("--retry-queue", type=Path)
    fallback = commands.add_parser("fallback")
    fallback.add_argument("--batch", type=Path, required=True)
    fallback.add_argument("--queue", type=Path)
    fallback.add_argument("--input", type=Path)
    fallback.add_argument("--output", type=Path, required=True)
    apply = commands.add_parser("apply")
    apply.add_argument("--data", type=Path, default=Path("packs/en/trans-vi/data.jsonl"))
    apply.add_argument("--queue", type=Path, required=True)
    apply.add_argument("--accepted", action="append", type=Path, required=True)
    apply.add_argument("--registry", type=Path, default=Path("packs/en/core/sense-ids.tsv"))
    apply.add_argument("--seed", type=Path, default=Path("packs/en/trans-vi/seed.jsonl"))
    apply.add_argument("--meta", type=Path, default=Path("packs/en/trans-vi/meta.json"))
    apply.add_argument("--allow-partial", action="store_true")
    apply.add_argument("--replace-invalid", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "queue":
        rows = build_queue(args.core, args.data, args.include_invalid); write_jsonl(args.output, rows); return len(rows)
    if args.command == "prepare":
        rows = build_requests(
            read_jsonl(args.queue), args.model, args.group_size, args.reasoning_effort
        ); write_jsonl(args.output, rows); return len(rows)
    if args.command == "shard":
        return len(shard_input(args.input, args.output_dir, args.max_bytes))
    if args.command == "submit":
        print(json.dumps(submit_batch(args.input, args.metadata, args.env, "trans-vi-rich-fields"), ensure_ascii=False)); return 0
    if args.command == "status":
        print(json.dumps(refresh_status(args.metadata, args.env), ensure_ascii=False)); return 0
    if args.command == "download":
        print(download_output(args.metadata, args.output, args.env)); return 0
    if args.command == "parse":
        if (args.queue is None) == (args.input is None):
            parser.error("parse requires exactly one of --queue or --input")
        source = read_jsonl(args.queue) if args.queue else rows_from_batch_input(args.input)
        rows, errors = parse_output(args.batch, {row["sense_id"]: row for row in source})
        if errors:
            if not args.allow_partial:
                raise ValueError("; ".join(errors[:20]))
            if args.retry_queue is None:
                parser.error("--retry-queue is required with --allow-partial")
            write_jsonl(args.output, rows)
            accepted_ids = {row["sense_id"] for row in rows}
            write_jsonl(args.retry_queue, [row for row in source if row["sense_id"] not in accepted_ids])
            return len(rows)
        write_jsonl(args.output, rows)
        return len(rows)
    if args.command == "fallback":
        if (args.queue is None) == (args.input is None):
            parser.error("fallback requires exactly one of --queue or --input")
        source = read_jsonl(args.queue) if args.queue else rows_from_batch_input(args.input)
        rows = fallback_rows(args.batch, {row["sense_id"]: row for row in source})
        write_jsonl(args.output, rows)
        return len(rows)
    count = apply_fields(args.data, args.accepted, args.queue, args.allow_partial, args.replace_invalid)
    build_canonical(args.registry, args.data, args.data, args.seed, args.meta)
    return count


if __name__ == "__main__":
    print(main())
