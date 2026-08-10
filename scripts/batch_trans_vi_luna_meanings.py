#!/usr/bin/env python3
"""Build and validate OpenAI Batch requests for concise Vietnamese meanings."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


SYSTEM_PROMPT = """You are a careful English-to-Vietnamese dictionary editor.
Write the compact dictionary headword for each supplied English sense, not a
translation or summary of its gloss. Use the word, part of speech, and gloss
only to disambiguate the sense; then discard incidental definition detail.
Return a natural common Vietnamese word or phrase, normally one to five words,
never a sentence, explanation, or incomplete grammatical fragment. Prefer an
idiomatic equivalent. Style examples: "place" → "nơi chốn", not "khu vực dành
cho mục đích riêng"; "company man" → "người của công ty", not a sentence
describing loyalty. Use a standard Vietnamese proper name when necessary; it
may use six words if shortening it would be unclear. Before returning, silently
count Vietnamese words and rewrite an overlong non-name into a shorter
equivalent."""

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

API_ROOT = "https://api.openai.com/v1"


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
                    "reasoning": {"effort": "low"},
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
    if not 1 <= len(meaning.split()) <= 10:
        return "meaning must contain 1 to 10 words"
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
        accepted.update(group)

    missing = expected_ids - set(accepted)
    errors.extend(f"missing sense_id {sense_id}" for sense_id in sorted(missing))
    return [accepted[sense_id] for sense_id in sorted(accepted)], errors


def require_complete_coverage(rows: list[dict[str, Any]], expected_ids: set[int]) -> None:
    """Refuse an apply step unless every expected sense occurs exactly once."""
    actual_ids: set[int] = set()
    duplicates: set[int] = set()
    for row in rows:
        sense_id = int(row["sense_id"])
        if sense_id in actual_ids:
            duplicates.add(sense_id)
        actual_ids.add(sense_id)
    if duplicates:
        raise ValueError(f"duplicate target sense_id {min(duplicates)}")
    unknown = actual_ids - expected_ids
    if unknown:
        raise ValueError(f"unknown target sense_id {min(unknown)}")
    missing = expected_ids - actual_ids
    if missing:
        raise ValueError(f"missing target sense_id {min(missing)}")


def read_jsonl(path: Path, limit: int | None = None, offset: int = 0) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows[offset : None if limit is None else offset + limit]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def load_api_key(env_path: Path = Path(".env")) -> str:
    """Load the API key without exporting or logging it."""
    if value := os.environ.get("OPENAI_API_KEY"):
        return value
    if not env_path.exists():
        raise RuntimeError("OPENAI_API_KEY is missing: no environment variable or .env file")
    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if line.startswith("OPENAI_API_KEY="):
            value = line.split("=", 1)[1].strip().strip('"').strip("'")
            if value:
                return value
    raise RuntimeError("OPENAI_API_KEY is missing from .env")


def api_request(path: str, method: str, key: str, body: bytes | None = None, content_type: str | None = None) -> Any:
    headers = {"Authorization": f"Bearer {key}"}
    if content_type:
        headers["Content-Type"] = content_type
    request = Request(API_ROOT + path, data=body, method=method, headers=headers)
    try:
        with urlopen(request, timeout=120) as response:
            content = response.read()
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API {error.code}: {detail}") from error
    return content


def api_json(path: str, method: str, key: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    response = api_request(path, method, key, body, "application/json" if body is not None else None)
    return json.loads(response)


def multipart_file(path: Path) -> tuple[bytes, str]:
    boundary = "----transViBatchBoundary"
    filename = path.name.encode("utf-8")
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    chunks = [
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"purpose\"\r\n\r\nbatch\r\n".encode(),
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"".encode() + filename
        + f"\"\r\nContent-Type: {content_type}\r\n\r\n".encode(),
        path.read_bytes(),
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def submit_batch(input_path: Path, metadata_path: Path, env_path: Path) -> dict[str, Any]:
    key = load_api_key(env_path)
    upload_body, content_type = multipart_file(input_path)
    file_result = json.loads(api_request("/files", "POST", key, upload_body, content_type))
    batch_result = api_json(
        "/batches",
        "POST",
        key,
        {
            "input_file_id": file_result["id"],
            "endpoint": "/v1/responses",
            "completion_window": "24h",
            "metadata": {"pipeline": "trans-vi-meaning"},
        },
    )
    metadata = {
        "batch_id": batch_result["id"],
        "input_file_id": file_result["id"],
        "status": batch_result["status"],
        "request_count": sum(1 for line in input_path.read_text(encoding="utf-8").splitlines() if line.strip()),
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def refresh_status(metadata_path: Path, env_path: Path) -> dict[str, Any]:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    result = api_json(f"/batches/{metadata['batch_id']}", "GET", load_api_key(env_path))
    metadata.update(
        {
            "status": result["status"],
            "output_file_id": result.get("output_file_id"),
            "error_file_id": result.get("error_file_id"),
            "request_counts": result.get("request_counts"),
        }
    )
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def download_output(metadata_path: Path, output_path: Path, env_path: Path) -> int:
    metadata = refresh_status(metadata_path, env_path)
    if metadata["status"] != "completed" or not metadata.get("output_file_id"):
        raise RuntimeError(f"Batch is {metadata['status']}; output is not ready")
    payload = api_request(f"/files/{metadata['output_file_id']}/content", "GET", load_api_key(env_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(payload)
    return len(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--queue", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--limit", type=int)
    prepare.add_argument("--offset", type=int, default=0)
    prepare.add_argument("--group-size", type=int, default=25)
    prepare.add_argument("--model", default="gpt-5.6-luna")

    submit = subparsers.add_parser("submit")
    submit.add_argument("--input", type=Path, required=True)
    submit.add_argument("--metadata", type=Path, required=True)
    submit.add_argument("--env", type=Path, default=Path(".env"))

    status = subparsers.add_parser("status")
    status.add_argument("--metadata", type=Path, required=True)
    status.add_argument("--env", type=Path, default=Path(".env"))

    download = subparsers.add_parser("download")
    download.add_argument("--metadata", type=Path, required=True)
    download.add_argument("--output", type=Path, required=True)
    download.add_argument("--env", type=Path, default=Path(".env"))

    parse = subparsers.add_parser("parse")
    parse.add_argument("--batch", type=Path, required=True)
    parse.add_argument("--queue", type=Path, required=True)
    parse.add_argument("--output", type=Path, required=True)
    parse.add_argument("--limit", type=int)
    parse.add_argument("--offset", type=int, default=0)
    parse.add_argument("--allow-partial", action="store_true")
    parse.add_argument("--retry-queue", type=Path)

    args = parser.parse_args(argv)
    if args.command == "prepare":
        requests = build_requests(read_jsonl(args.queue, args.limit, args.offset), args.model, args.group_size)
        write_jsonl(args.output, requests)
        return len(requests)
    if args.command == "submit":
        print(json.dumps(submit_batch(args.input, args.metadata, args.env), ensure_ascii=False))
        return 0
    if args.command == "status":
        print(json.dumps(refresh_status(args.metadata, args.env), ensure_ascii=False))
        return 0
    if args.command == "download":
        print(download_output(args.metadata, args.output, args.env))
        return 0
    if args.command == "parse":
        source_rows = read_jsonl(args.queue, args.limit, args.offset)
        expected_ids = {int(row["sense_id"]) for row in source_rows}
        rows, errors = parse_output(args.batch, expected_ids)
        if errors:
            if args.allow_partial:
                if args.retry_queue is None:
                    raise ValueError("--retry-queue is required with --allow-partial")
                write_jsonl(args.output, rows)
                accepted_ids = {int(row["sense_id"]) for row in rows}
                write_jsonl(args.retry_queue, [row for row in source_rows if int(row["sense_id"]) not in accepted_ids])
                return len(rows)
            raise ValueError("; ".join(errors[:20]))
        require_complete_coverage(rows, expected_ids)
        write_jsonl(args.output, rows)
        return len(rows)
    raise AssertionError(f"unsupported command {args.command}")


if __name__ == "__main__":
    print(main())
