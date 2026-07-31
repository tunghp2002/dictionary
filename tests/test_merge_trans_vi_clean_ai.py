import json
import tempfile
import unittest
from pathlib import Path

from scripts.merge_trans_vi_clean_ai import merge_clean_ai_batches


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def record(sense_id: int, meaning: str, description: str = "A gloss.") -> dict:
    return {
        "sense_id": sense_id,
        "meaning": meaning,
        "description": description,
        "examples": [{"en": "New example.", "vi": "Ví dụ mới."}],
        "collocations": ["new phrase"],
    }


class MergeTransViCleanAiTest(unittest.TestCase):
    def test_replaces_all_target_fields_without_seed_leakage(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            seed = root / "seed.jsonl"
            batch = root / "batch.jsonl"
            output = root / "out.jsonl"
            old = record(2, "nghĩa cũ", "Old description.")
            old["examples"] = [{"en": "Old example.", "vi": "Ví dụ cũ."}]
            old["collocations"] = ["old phrase"]
            write_jsonl(seed, [old, record(99, "ngoài mục tiêu")])
            fresh = record(2, "nghĩa mới", "Fresh English description.")
            write_jsonl(batch, [fresh])

            self.assertEqual(merge_clean_ai_batches([batch], seed, {2}, output), 1)
            rows = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(rows, [fresh, record(99, "ngoài mục tiêu")])

    def test_requires_complete_target_coverage(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            seed = root / "seed.jsonl"
            batch = root / "batch.jsonl"
            output = root / "out.jsonl"
            write_jsonl(seed, [])
            write_jsonl(batch, [record(2, "một")])
            with self.assertRaisesRegex(ValueError, "missing AI target"):
                merge_clean_ai_batches([batch], seed, {2, 3}, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
