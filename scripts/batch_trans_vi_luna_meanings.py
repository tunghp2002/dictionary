#!/usr/bin/env python3
"""Build and validate OpenAI Batch requests for concise Vietnamese meanings."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


SYSTEM_PROMPT = """You are a careful English-to-Vietnamese dictionary editor.
For each supplied English sense, write exactly one short, natural Vietnamese
dictionary meaning. Use the word, part of speech, and gloss to choose the
correct sense. Do not translate or abbreviate the English gloss word by word.
Return a common Vietnamese word or phrase of one to five words, never an
English description, sentence, or incomplete grammatical fragment."""

RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"sense_id": {"type": "integer"}, "meaning": {"type": "string"}},
                "required": ["sense_id", "meaning"],
            },
        }
    },
    "required": ["translations"],
}


def build_requests(rows: list[dict[str, Any]], model: str, group_size: int) -> list[dict[str, Any]]:
    """Build ordered Responses Batch requests without changing the source rows."""
    if group_size < 1:
        raise ValueError("group_size must be positive")
    requests: list[dict[str, Any]] = []
    for offset in range(0, len(rows), group_size):
        group = rows[offset : offset + group_size]
        for row in group:
            if set(row) != {"sense_id", "word", "pos", "gloss"}:
                raise ValueError(f"invalid queue fields for {row.get('sense_id')}")
        context = json.dumps(group, ensure_ascii=False, separators=(",", ":"))
        requests.append(
            {
                "custom_id": f"meaning-{len(requests) + 1:06d}",
                "method": "POST",
                "url": "/v1/responses",
                "body": {
                    "model": model,
                    "input": [
                        {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]},
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": "Translate every input row and preserve its sense_id exactly. Input JSON:\n" + context,
                                }
                            ],
                        },
                    ],
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "vietnamese_meanings",
                            "strict": True,
                            "schema": RESPONSE_SCHEMA,
                        },
                        "verbosity": "low",
                    },
                },
            }
        )
    return requests


def validate_meaning(value: Any) -> str | None:
    """Return the first deterministic quality error, if a meaning is unusable."""
    if not isinstance(value, str) or not value.strip():
        return "empty meaning"
    meaning = value.strip()
    if len(meaning) > 35:
        return "meaning exceeds 35 characters"
    if not 1 <= len(meaning.split()) <= 5:
        return "meaning must contain 1 to 5 words"
    if any("\u4e00" <= char <= "\u9fff" for char in meaning):
        return "CJK text in meaning"
    if meaning.casefold() == "được thực hiện với ít":
        return "likely fragment"
    return None


def _output_text(body: dict[str, Any]) -> str | None:
    direct = body.get("output_text")
    if isinstance(direct, str):
        return direct
    for item in body.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    return None


def parse_output(path: Path, expected_ids: set[int]) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse Batch output and reject malformed, duplicate, unknown, and weak rows."""
    accepted: dict[int, dict[str, Any]] = {}
    errors: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            result = json.loads(line)
            custom_id = str(result["custom_id"])
            response = result["response"]
            if int(response["status_code"]) != 200:
                raise ValueError(f"HTTP {response['status_code']}")
            payload = json.loads(_output_text(response["body"]) or "")
            translations = payload["translations"]
            if not isinstance(translations, list):
                raise ValueError("translations is not an array")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"line {line_number}: invalid Batch response ({error})")
            continue

        group: dict[int, dict[str, Any]] = {}
        group_errors: list[str] = []
        for translation in translations:
            if not isinstance(translation, dict) or set(translation) != {"sense_id", "meaning"}:
                group_errors.append(f"{custom_id}: invalid translation record")
                continue
            sense_id = translation["sense_id"]
            if not isinstance(sense_id, int):
                group_errors.append(f"{custom_id}: invalid sense_id {sense_id}")
                continue
            if sense_id not in expected_ids:
                group_errors.append(f"{custom_id}: unknown sense_id {sense_id}")
                continue
            if sense_id in accepted or sense_id in group:
                group_errors.append(f"{custom_id}: duplicate sense_id {sense_id}")
                continue
            quality_error = validate_meaning(translation["meaning"])
            if quality_error:
                group_errors.append(f"{custom_id}: {quality_error} for sense_id {sense_id}")
                continue
            group[sense_id] = {"sense_id": sense_id, "meaning": translation["meaning"].strip()}
        if group_errors:
            errors.extend(group_errors)
            continue
        accepted.update(group)

    missing = expected_ids - set(accepted)
    errors.extend(f"missing sense_id {sense_id}" for sense_id in sorted(missing))
    return [accepted[sense_id] for sense_id in sorted(accepted)], errors
