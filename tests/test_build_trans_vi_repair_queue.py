import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_trans_vi_repair_queue import build_repair_queue


class BuildTransViRepairQueueTest(unittest.TestCase):
    def test_queues_target_rows_with_empty_or_non_concise_meanings_without_truncating_them(self):
        rows = [
            {
                "sense_id": 1,
                "word": "businessman",
                "pos": "noun",
                "gloss": ["a man engaged in commercial or industrial business"],
                "current_meaning": "người đàn ông tham gia kinh doanh thương mại hoặc công nghiệp",
                "examples": [{"en": "He is a businessman.", "vi": "Ông ấy là doanh nhân."}],
                "collocations": ["businessman of the year"],
            },
            {"sense_id": 2, "word": "brief", "pos": "adj", "gloss": ["short"], "current_meaning": "ngắn gọn", "examples": [], "collocations": []},
            {"sense_id": 3, "word": "outside", "pos": "noun", "gloss": ["not targeted"], "current_meaning": "", "examples": [], "collocations": []},
        ]
        manifest = {"target_sense_ids": [1, 2]}
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            queue = root / "queue.jsonl"
            manifest_path = root / "target-manifest.json"
            output = root / "repair-queue.jsonl"
            queue.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            count = build_repair_queue(queue, manifest_path, output)
            records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(count, 1)
        self.assertEqual(records, [{
            "sense_id": 1,
            "word": "businessman",
            "pos": "noun",
            "gloss": ["a man engaged in commercial or industrial business"],
            "current_meaning": "người đàn ông tham gia kinh doanh thương mại hoặc công nghiệp",
            "examples": [{"en": "He is a businessman.", "vi": "Ông ấy là doanh nhân."}],
            "collocations": ["businessman of the year"],
        }])


if __name__ == "__main__":
    unittest.main()
