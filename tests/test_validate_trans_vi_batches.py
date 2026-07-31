import json
import tempfile
import unittest
from pathlib import Path

from scripts.merge_trans_vi_batches import merge_batches
from scripts.validate_trans_vi_batches import validate_batch


FIELDS = {"sense_id", "meaning", "description", "examples", "collocations"}


def record(sense_id, meaning="nghĩa", description="A short English gloss."):
    return {
        "sense_id": sense_id,
        "meaning": meaning,
        "description": description,
        "examples": [],
        "collocations": [],
    }


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


class ValidateTransViBatchesTest(unittest.TestCase):
    def test_rejects_invalid_records_in_stable_order(self):
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "batch.jsonl"
            write_jsonl(
                path,
                [
                    record(2),
                    record(2),
                    record(9),
                    record(3, description=""),
                    record(4, meaning="x" * 36),
                    record(5, meaning="中文"),
                    {"sense_id": 6, "meaning": "hợp lệ"},
                ],
            )

            self.assertEqual(
                validate_batch(path, {2, 3, 4, 5, 6}),
                [
                    "line 2: duplicate sense_id 2",
                    "line 3: non-target sense_id 9",
                    "line 4: empty description for sense_id 3",
                    "line 5: meaning exceeds 35 characters for sense_id 4",
                    "line 6: CJK text in meaning for sense_id 5",
                    "line 7: invalid fields for sense_id 6",
                ],
            )

    def test_allows_empty_descriptions_when_not_required(self):
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "batch.jsonl"
            write_jsonl(path, [record(2, description="")])
            self.assertEqual(validate_batch(path, {2}, require_descriptions=False), [])

    def test_reports_malformed_json_as_an_error(self):
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "batch.jsonl"
            path.write_text("{not json}\n", encoding="utf-8")
            self.assertEqual(validate_batch(path, {2}), ["line 1: invalid JSON"])

    def test_rejects_nested_field_drift_and_reports_combined_meaning_errors(self):
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "batch.jsonl"
            bad_example = record(2)
            bad_example["examples"] = [{"en": "source"}]
            bad_collocations = record(3)
            bad_collocations["collocations"] = ["valid", 4]
            combined = record(4, meaning="中" * 36)
            write_jsonl(path, [record(1, meaning="x" * 35), bad_example, bad_collocations, combined])

            self.assertEqual(
                validate_batch(path, {1, 2, 3, 4}),
                [
                    "line 2: invalid examples for sense_id 2",
                    "line 3: invalid collocations for sense_id 3",
                    "line 4: CJK text in meaning for sense_id 4",
                    "line 4: meaning exceeds 35 characters for sense_id 4",
                ],
            )

    def test_merge_is_idempotent_and_preserves_non_target_seed_records(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            seed, batch, output = root / "seed.jsonl", root / "batch.jsonl", root / "output.jsonl"
            non_target = record(99, "seed", "")
            write_jsonl(seed, [non_target, record(2, "old")])
            write_jsonl(batch, [record(3), record(2, "new")])

            self.assertEqual(merge_batches([batch], seed, {2, 3}, output), 2)
            first = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(first, [record(2, "new"), record(3), non_target])
            self.assertEqual(merge_batches([batch], output, {2, 3}, output), 2)
            self.assertEqual(output.read_text(encoding="utf-8").splitlines(), [json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in first])

    def test_merge_normalizes_legacy_seed_records_before_validation(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            seed, batch, output = root / "seed.jsonl", root / "batch.jsonl", root / "out.jsonl"
            legacy_non_target = {"sense_id": 99, "meaning": "seed", "examples": [], "collocations": []}
            legacy_target = {"sense_id": 2, "meaning": "old", "examples": [], "collocations": []}
            write_jsonl(seed, [legacy_non_target, legacy_target])
            write_jsonl(batch, [record(2, "new", "Replacement gloss.")])

            self.assertEqual(merge_batches([batch], seed, {2}, output), 1)
            self.assertEqual(
                [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()],
                [record(2, "new", "Replacement gloss."), record(99, "seed", "")],
            )

    def test_merge_rejects_conflicting_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            first, second, seed, output = root / "one.jsonl", root / "two.jsonl", root / "seed.jsonl", root / "out.jsonl"
            write_jsonl(first, [record(2, "một")])
            write_jsonl(second, [record(2, "hai")])
            write_jsonl(seed, [])

            with self.assertRaisesRegex(ValueError, "conflicting sense_id 2"):
                merge_batches([first, second], seed, {2}, output)
            self.assertFalse(output.exists())

    def test_merge_accepts_repeated_identical_batches(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            batch, seed, output = root / "batch.jsonl", root / "seed.jsonl", root / "out.jsonl"
            write_jsonl(batch, [record(2)])
            write_jsonl(seed, [])
            self.assertEqual(merge_batches([batch, batch], seed, {2}, output), 1)

    def test_merge_rejects_invalid_seed_before_writing(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            batch, seed, output = root / "batch.jsonl", root / "seed.jsonl", root / "out.jsonl"
            write_jsonl(batch, [record(2)])
            write_jsonl(seed, [{"sense_id": "invalid", "meaning": "x"}])
            with self.assertRaisesRegex(ValueError, "invalid seed.*invalid sense_id"):
                merge_batches([batch], seed, {2}, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
