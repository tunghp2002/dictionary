#!/usr/bin/env python3
"""Validate staged English-to-Vietnamese translation batches."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


TRANSLATION_FIELDS = {"sense_id", "meaning", "description", "examples", "collocations"}
LEGACY_TRANSLATION_FIELDS = TRANSLATION_FIELDS - {"description"}
CJK_RANGES = ((0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF))


def has_cjk(value: str) -> bool:
    return any(start <= ord(char) <= end for char in value for start, end in CJK_RANGES)


def read_records(path: Path) -> list[tuple[int, dict[str, Any]]]:
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            records.append((line_number, json.loads(line)))
    return records


def normalize_legacy_seed_record(record: dict[str, Any]) -> dict[str, Any]:
    """Add the required empty description to an otherwise valid legacy record."""
    if set(record) == LEGACY_TRANSLATION_FIELDS:
        return {**record, "description": ""}
    return record


def _validate(path: Path, target_ids: set[int], require_descriptions: bool, reject_non_targets: bool, normalize_legacy: bool = False) -> list[str]:
    errors: list[str] = []
    seen: set[int] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            errors.append(f"line {line_number}: invalid JSON")
            continue
        if not isinstance(record, dict):
            errors.append(f"line {line_number}: record is not an object")
            continue
        if normalize_legacy:
            record = normalize_legacy_seed_record(record)
        sense_id = record.get("sense_id")
        if not isinstance(sense_id, int) or isinstance(sense_id, bool):
            errors.append(f"line {line_number}: invalid sense_id")
            continue
        if sense_id in seen:
            errors.append(f"line {line_number}: duplicate sense_id {sense_id}")
            continue
        seen.add(sense_id)
        is_target = sense_id in target_ids
        if reject_non_targets and not is_target:
            errors.append(f"line {line_number}: non-target sense_id {sense_id}")
        if set(record) != TRANSLATION_FIELDS:
            errors.append(f"line {line_number}: invalid fields for sense_id {sense_id}")
            continue
        meaning = record["meaning"]
        description = record["description"]
        if not isinstance(meaning, str) or not isinstance(description, str):
            errors.append(f"line {line_number}: invalid text fields for sense_id {sense_id}")
            continue
        if is_target:
            if not meaning.strip():
                errors.append(f"line {line_number}: empty meaning for sense_id {sense_id}")
            if len(meaning) > 35:
                errors.append(f"line {line_number}: meaning exceeds 35 characters for sense_id {sense_id}")
            if has_cjk(meaning):
                errors.append(f"line {line_number}: CJK text in meaning for sense_id {sense_id}")
        if is_target and require_descriptions and not description.strip():
            errors.append(f"line {line_number}: empty description for sense_id {sense_id}")
        examples = record["examples"]
        if not isinstance(examples, list) or any(
            not isinstance(example, dict)
            or set(example) != {"en", "vi"}
            or not isinstance(example["en"], str)
            or not isinstance(example["vi"], str)
            for example in examples
        ):
            errors.append(f"line {line_number}: invalid examples for sense_id {sense_id}")
        collocations = record["collocations"]
        if not isinstance(collocations, list) or not all(isinstance(item, str) for item in collocations):
            errors.append(f"line {line_number}: invalid collocations for sense_id {sense_id}")
    return sorted(errors)


def validate_batch(path: Path, target_ids: set[int], require_descriptions: bool = True) -> list[str]:
    """Return deterministic validation errors for a staged JSONL batch."""
    return _validate(path, target_ids, require_descriptions, reject_non_targets=True)


def validate_seed(path: Path, target_ids: set[int], require_descriptions: bool = True) -> list[str]:
    """Validate seed schema while allowing non-target placeholder records."""
    return _validate(path, target_ids, require_descriptions=require_descriptions, reject_non_targets=False, normalize_legacy=True)
