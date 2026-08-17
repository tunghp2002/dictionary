#!/usr/bin/env python3
"""Fill missing English dictionary descriptions with an OpenAI Batch."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

try:
    from scripts.batch_trans_vi_luna_meanings import api_json, api_request, load_api_key, multipart_file
    from scripts.build_core_en import load_id_registry
    from scripts.build_trans_vi_canonical import build_canonical
except ModuleNotFoundError:  # direct script execution
    from batch_trans_vi_luna_meanings import api_json, api_request, load_api_key, multipart_file
    from build_core_en import load_id_registry
    from build_trans_vi_canonical import build_canonical


QUEUE_FIELDS = {"sense_id", "word", "pos", "gloss"}
DESCRIPTION_FIELDS = {"sense_id", "description"}
SYSTEM_PROMPT = """You are a careful English dictionary editor. For every supplied sense, write one concise English dictionary description based strictly on its source gloss. Preserve distinctions between senses and parts of speech. Return a capitalized, punctuated, non-empty English sentence. Do not add translations, examples, commentary, or fields."""
RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "descriptions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"sense_id": {"type": "integer"}, "description": {"type": "string"}},
                "required": ["sense_id", "description"],
            },
        },
    },
    "required": ["descriptions"],
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows), encoding="utf-8")


def load_oewn_glosses(oewn_dir: Path) -> dict[str, str]:
    """Map each OEWN sense key to the concatenated definition of its synset."""
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    sense_synsets: dict[str, str] = {}
    for path in sorted((oewn_dir / "src/yaml").glob("entries-*.yaml")):
        with path.open(encoding="utf-8") as handle:
            entries = yaml.load(handle, Loader=loader)
        for parts in entries.values():
            for part in parts.values():
                for sense in part.get("sense", ()):
                    sense_synsets[str(sense["id"])] = str(sense["synset"])

    definitions: dict[str, str] = {}
    for path in sorted((oewn_dir / "src/yaml").glob("*.yaml")):
        if path.name.startswith(("entries-", "frames")):
            continue
        with path.open(encoding="utf-8") as handle:
            synsets = yaml.load(handle, Loader=loader)
        for synset, item in synsets.items():
            definition = item.get("definition", ())
            if definition:
                definitions[str(synset)] = " ".join(str(value).strip() for value in definition if str(value).strip())

    glosses = {}
    for sense_key, synset in sense_synsets.items():
        if gloss := definitions.get(synset, "").strip():
            glosses[sense_key] = gloss
    return glosses


def build_queue(core_path: Path, data_path: Path, registry_path: Path, oewn_dir: Path) -> list[dict[str, Any]]:
    """Return source-backed rows for every translation record with no description."""
    core = {
        sense["id"]: {"word": row["word"], "pos": sense["pos"]}
        for row in read_jsonl(core_path)
        for sense in row["senses"]
    }
    descriptions = {row["sense_id"]: row["description"] for row in read_jsonl(data_path)}
    if set(core) != set(descriptions):
        raise ValueError("core and translation sense IDs differ")
    registry = load_id_registry(registry_path)
    source_keys = {sense_id: source_key for source_key, sense_id in registry.items()}
    glosses = load_oewn_glosses(oewn_dir)
    queue = []
    for sense_id in sorted(core):
        if str(descriptions[sense_id]).strip():
            continue
        source_key = source_keys.get(sense_id)
        gloss = glosses.get(source_key or "")
        if not gloss:
            raise ValueError(f"missing OEWN gloss for sense_id {sense_id}")
        queue.append({"sense_id": sense_id, **core[sense_id], "gloss": gloss})
    return queue


def build_requests(rows: list[dict[str, Any]], model: str, group_size: int) -> list[dict[str, Any]]:
    if not 1 <= group_size <= 25:
        raise ValueError("group_size must be between 1 and 25")
    requests = []
    for offset in range(0, len(rows), group_size):
        group = rows[offset : offset + group_size]
        if any(set(row) != QUEUE_FIELDS for row in group):
            raise ValueError("invalid description queue fields")
        requests.append({
            "custom_id": f"description-{len(requests) + 1:06d}",
            "method": "POST",
            "url": "/v1/responses",
            "body": {
                "model": model,
                "input": [
                    {"role": "system", "content": [{"type": "input_text", "text": SYSTEM_PROMPT}]},
                    {"role": "user", "content": [{"type": "input_text", "text": "Return one description for every input row. Input JSON:\n" + json.dumps(group, ensure_ascii=False, separators=(",", ":"))}]},
                ],
                "text": {"format": {"type": "json_schema", "name": "dictionary_descriptions", "strict": True, "schema": RESPONSE_SCHEMA}, "verbosity": "low"},
                "reasoning": {"effort": "low"},
            },
        })
    return requests


def rows_from_batch_input(path: Path) -> list[dict[str, Any]]:
    """Recover the source rows embedded in a generated Batch input file."""
    rows: list[dict[str, Any]] = []
    for number, request in enumerate(read_jsonl(path), 1):
        try:
            text = request["body"]["input"][1]["content"][0]["text"]
            prefix = "Return one description for every input row. Input JSON:\n"
            group = json.loads(text.removeprefix(prefix))
        except (AttributeError, IndexError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise ValueError(f"input line {number}: invalid description Batch request") from error
        if not text.startswith(prefix) or not isinstance(group, list) or any(set(row) != QUEUE_FIELDS for row in group):
            raise ValueError(f"input line {number}: invalid description Batch request")
        rows.extend(group)
    if len({row["sense_id"] for row in rows}) != len(rows):
        raise ValueError("description Batch input has duplicate sense IDs")
    return rows


def shard_input(input_path: Path, output_dir: Path, max_bytes: int) -> list[Path]:
    """Split a valid Batch JSONL file at line boundaries for token-queue limits."""
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    shards: list[Path] = []
    payload = bytearray()
    for line in input_path.read_bytes().splitlines(keepends=True):
        if len(line) > max_bytes:
            raise ValueError("Batch request exceeds max_bytes")
        if payload and len(payload) + len(line) > max_bytes:
            path = output_dir / f"input-{len(shards) + 1:03d}.jsonl"
            path.write_bytes(payload)
            shards.append(path)
            payload = bytearray()
        payload.extend(line)
    if payload:
        path = output_dir / f"input-{len(shards) + 1:03d}.jsonl"
        path.write_bytes(payload)
        shards.append(path)
    return shards


def _output_text(body: dict[str, Any]) -> str | None:
    if isinstance(body.get("output_text"), str):
        return body["output_text"]
    for item in body.get("output", []):
        for content in item.get("content", []):
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                return content["text"]
    return None


def validate_description(value: Any) -> str | None:
    if not isinstance(value, str) or not (description := value.strip()):
        return "empty description"
    if len(description) > 500:
        return "description exceeds 500 characters"
    if description.rstrip("”’")[-1] not in ".!?":
        return "description must end with sentence punctuation"
    if any("\u4e00" <= char <= "\u9fff" for char in description):
        return "CJK text in description"
    return None


def parse_output(path: Path, expected_ids: set[int]) -> tuple[list[dict[str, Any]], list[str]]:
    accepted: dict[int, dict[str, Any]] = {}
    errors: list[str] = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            result = json.loads(line)
            response = result["response"]
            if int(response["status_code"]) != 200:
                raise ValueError(f"HTTP {response['status_code']}")
            descriptions = json.loads(_output_text(response["body"]) or "")["descriptions"]
            if not isinstance(descriptions, list):
                raise ValueError("descriptions is not an array")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"line {number}: invalid Batch response ({error})")
            continue
        for row in descriptions:
            sense_id = row.get("sense_id") if isinstance(row, dict) else None
            if not isinstance(row, dict) or set(row) != DESCRIPTION_FIELDS:
                errors.append(f"line {number}: invalid description record")
            elif not isinstance(sense_id, int) or sense_id not in expected_ids:
                errors.append(f"line {number}: unknown sense_id {sense_id}")
            elif sense_id in accepted:
                errors.append(f"line {number}: duplicate sense_id {sense_id}")
            elif error := validate_description(row["description"]):
                errors.append(f"line {number}: {error} for sense_id {sense_id}")
            else:
                accepted[sense_id] = {"sense_id": sense_id, "description": row["description"].strip()}
    errors.extend(f"missing sense_id {sense_id}" for sense_id in sorted(expected_ids - set(accepted)))
    return [accepted[sense_id] for sense_id in sorted(accepted)], errors


def apply_descriptions(data_path: Path, accepted_paths: Path | list[Path], queue_path: Path) -> int:
    """Replace descriptions only for exactly the queued, currently blank senses."""
    queue = read_jsonl(queue_path)
    source = queue if all("sense_id" in row for row in queue) else rows_from_batch_input(queue_path)
    expected = {row["sense_id"] for row in source}
    accepted: dict[int, dict[str, Any]] = {}
    for accepted_path in [accepted_paths] if isinstance(accepted_paths, Path) else accepted_paths:
        for row in read_jsonl(accepted_path):
            sense_id = row.get("sense_id") if isinstance(row, dict) else None
            if sense_id in accepted:
                raise ValueError(f"duplicate accepted sense_id {sense_id}")
            accepted[sense_id] = row
    if set(accepted) != expected or any(set(row) != DESCRIPTION_FIELDS or validate_description(row["description"]) for row in accepted.values()):
        raise ValueError("accepted descriptions do not exactly cover the queue")
    records = read_jsonl(data_path)
    for row in records:
        sense_id = row["sense_id"]
        if sense_id in accepted:
            if row["description"].strip():
                raise ValueError(f"description is no longer blank for sense_id {sense_id}")
            row["description"] = accepted[sense_id]["description"].strip()
    write_jsonl(data_path.with_suffix(data_path.suffix + ".tmp"), records)
    data_path.with_suffix(data_path.suffix + ".tmp").replace(data_path)
    return len(accepted)


def submit_batch(input_path: Path, metadata_path: Path, env_path: Path, pipeline: str = "trans-vi-description") -> dict[str, Any]:
    key = load_api_key(env_path)
    body, content_type = multipart_file(input_path)
    file_result = json.loads(api_request("/files", "POST", key, body, content_type))
    batch = api_json("/batches", "POST", key, {"input_file_id": file_result["id"], "endpoint": "/v1/responses", "completion_window": "24h", "metadata": {"pipeline": pipeline}})
    metadata = {"batch_id": batch["id"], "input_file_id": file_result["id"], "status": batch["status"], "request_count": len(read_jsonl(input_path))}
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def refresh_status(metadata_path: Path, env_path: Path) -> dict[str, Any]:
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    batch = api_json(f"/batches/{metadata['batch_id']}", "GET", load_api_key(env_path))
    metadata.update({"status": batch["status"], "errors": batch.get("errors"), "output_file_id": batch.get("output_file_id"), "error_file_id": batch.get("error_file_id"), "request_counts": batch.get("request_counts")})
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return metadata


def download_output(metadata_path: Path, output_path: Path, env_path: Path) -> int:
    metadata = refresh_status(metadata_path, env_path)
    if metadata["status"] not in {"completed", "cancelled"} or not metadata.get("output_file_id"):
        raise RuntimeError(f"Batch is {metadata['status']}; output is not ready")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(api_request(f"/files/{metadata['output_file_id']}/content", "GET", load_api_key(env_path)))
    return output_path.stat().st_size


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    queue = commands.add_parser("queue")
    queue.add_argument("--core", type=Path, default=Path("packs/en/core/data.jsonl"))
    queue.add_argument("--data", type=Path, default=Path("packs/en/trans-vi/data.jsonl"))
    queue.add_argument("--registry", type=Path, default=Path("packs/en/core/sense-ids.tsv"))
    queue.add_argument("--oewn", type=Path, default=Path(".cache/sources/oewn-2025"))
    queue.add_argument("--output", type=Path, required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--queue", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    prepare.add_argument("--group-size", type=int, default=25)
    prepare.add_argument("--model", default="gpt-5.6-luna")
    shard = commands.add_parser("shard")
    shard.add_argument("--input", type=Path, required=True)
    shard.add_argument("--output-dir", type=Path, required=True)
    shard.add_argument("--max-bytes", type=int, required=True)
    submit = commands.add_parser("submit")
    submit.add_argument("--input", type=Path, required=True)
    submit.add_argument("--metadata", type=Path, required=True)
    submit.add_argument("--env", type=Path, default=Path(".env"))
    status = commands.add_parser("status")
    status.add_argument("--metadata", type=Path, required=True)
    status.add_argument("--env", type=Path, default=Path(".env"))
    download = commands.add_parser("download")
    download.add_argument("--metadata", type=Path, required=True)
    download.add_argument("--output", type=Path, required=True)
    download.add_argument("--env", type=Path, default=Path(".env"))
    parse = commands.add_parser("parse")
    parse.add_argument("--batch", type=Path, required=True)
    parse.add_argument("--queue", type=Path)
    parse.add_argument("--input", type=Path)
    parse.add_argument("--output", type=Path, required=True)
    parse.add_argument("--allow-partial", action="store_true")
    parse.add_argument("--retry-queue", type=Path)
    apply = commands.add_parser("apply")
    apply.add_argument("--data", type=Path, default=Path("packs/en/trans-vi/data.jsonl"))
    apply.add_argument("--queue", type=Path, required=True)
    apply.add_argument("--accepted", action="append", type=Path, required=True)
    apply.add_argument("--registry", type=Path, default=Path("packs/en/core/sense-ids.tsv"))
    apply.add_argument("--seed", type=Path, default=Path("packs/en/trans-vi/seed.jsonl"))
    apply.add_argument("--meta", type=Path, default=Path("packs/en/trans-vi/meta.json"))
    args = parser.parse_args(argv)
    if args.command == "queue":
        rows = build_queue(args.core, args.data, args.registry, args.oewn); write_jsonl(args.output, rows); return len(rows)
    if args.command == "prepare":
        rows = build_requests(read_jsonl(args.queue), args.model, args.group_size); write_jsonl(args.output, rows); return len(rows)
    if args.command == "shard":
        return len(shard_input(args.input, args.output_dir, args.max_bytes))
    if args.command == "submit":
        print(json.dumps(submit_batch(args.input, args.metadata, args.env), ensure_ascii=False)); return 0
    if args.command == "status":
        print(json.dumps(refresh_status(args.metadata, args.env), ensure_ascii=False)); return 0
    if args.command == "download":
        print(download_output(args.metadata, args.output, args.env)); return 0
    if args.command == "parse":
        if (args.queue is None) == (args.input is None):
            parser.error("parse requires exactly one of --queue or --input")
        source = read_jsonl(args.queue) if args.queue else rows_from_batch_input(args.input)
        rows, errors = parse_output(args.batch, {row["sense_id"] for row in source})
        if errors:
            if not args.allow_partial:
                raise ValueError("; ".join(errors[:20]))
            if args.retry_queue is None:
                parser.error("--retry-queue is required with --allow-partial")
            write_jsonl(args.output, rows)
            accepted_ids = {row["sense_id"] for row in rows}
            write_jsonl(args.retry_queue, [row for row in source if row["sense_id"] not in accepted_ids])
            return len(rows)
        write_jsonl(args.output, rows); return len(rows)
    count = apply_descriptions(args.data, args.accepted, args.queue)
    build_canonical(args.registry, args.data, args.data, args.seed, args.meta)
    return count


if __name__ == "__main__":
    print(main())
