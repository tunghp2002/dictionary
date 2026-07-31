import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_trans_vi_batches import build_batches
from scripts.validate_trans_vi_batches import validate_batch


class BuildTransViBatchesTest(unittest.TestCase):
    def test_builds_ordered_batches_with_vietnamese_fallbacks(self):
        rows = [
            {"sense_id": 1, "word": "a", "pos": "noun", "gloss": ["first gloss", "second gloss"], "current_meaning": "nghĩa ngắn", "description": "old", "examples": [{"en": "e", "vi": "v"}], "collocations": ["c"]},
            {"sense_id": 2, "word": "b", "pos": "noun", "gloss": ["a measuring unit"], "current_meaning": "một đơn vị đo chiều dài trong hệ mét", "description": "", "examples": [], "collocations": []},
            {"sense_id": 3, "word": "c", "pos": "noun", "gloss": ["a tick species"], "current_meaning": "", "description": "", "examples": [], "collocations": []},
        ]
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            queue = root / "queue.jsonl"
            queue.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
            result = build_batches(queue, root / "batches", 2)
            first = [json.loads(line) for line in (root / "batches" / "batch-001.jsonl").read_text(encoding="utf-8").splitlines()]
            second = [json.loads(line) for line in (root / "batches" / "batch-002.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(result, {"batches": 2, "records": 3, "preserved": 1, "compacted": 1, "filled_empty": 1})
        self.assertEqual(first[0], {"sense_id": 1, "meaning": "nghĩa ngắn", "description": "first gloss second gloss", "examples": [{"en": "e", "vi": "v"}], "collocations": ["c"]})
        self.assertEqual(first[1]["meaning"], "đơn vị đo chiều dài")
        self.assertEqual(second[0]["meaning"], "danh từ")

    def test_uses_pos_fallback_for_english_current_meaning_and_passes_validator(self):
        row = {"sense_id": 4, "word": "d", "pos": "verb", "gloss": ["to move"], "current_meaning": "to move quickly", "examples": [], "collocations": []}
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            queue = root / "queue.jsonl"
            queue.write_text(json.dumps(row) + "\n", encoding="utf-8")
            build_batches(queue, root / "batches")
            batch = root / "batches" / "batch-001.jsonl"
            record = json.loads(batch.read_text(encoding="utf-8"))
            errors = validate_batch(batch, {4})
        self.assertEqual(record["meaning"], "động từ")
        self.assertEqual(errors, [])

    def test_rejects_batch_size_outside_one_to_250(self):
        with tempfile.TemporaryDirectory() as temp_name:
            queue = Path(temp_name) / "queue.jsonl"
            queue.write_text("", encoding="utf-8")
            for batch_size in (0, 251):
                with self.subTest(batch_size=batch_size):
                    with self.assertRaises(ValueError):
                        build_batches(queue, Path(temp_name) / "batches", batch_size)

    def test_removes_stale_batch_files_before_writing(self):
        row = {"sense_id": 5, "word": "e", "pos": "noun", "gloss": ["a thing"], "current_meaning": "nghĩa ngắn", "examples": [], "collocations": []}
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            queue = root / "queue.jsonl"
            output_dir = root / "batches"
            output_dir.mkdir()
            (output_dir / "batch-999.jsonl").write_text("stale\n", encoding="utf-8")
            queue.write_text(json.dumps(row) + "\n", encoding="utf-8")
            build_batches(queue, output_dir)
            names = sorted(path.name for path in output_dir.glob("batch-*.jsonl"))
        self.assertEqual(names, ["batch-001.jsonl"])


if __name__ == "__main__":
    unittest.main()
