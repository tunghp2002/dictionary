import json
import tempfile
import unittest
from pathlib import Path

from scripts.batch_trans_vi_luna_meanings import build_requests, parse_output


class BatchLunaMeaningTest(unittest.TestCase):
    def write_output(self, row: dict) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "output.jsonl"
        path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def test_build_requests_keeps_each_group_and_uses_strict_schema(self):
        rows = [
            {"sense_id": 1, "word": "quick", "pos": "adjective", "gloss": ["moving fast"]},
            {"sense_id": 2, "word": "quick", "pos": "adjective", "gloss": ["alive"]},
        ]

        requests = build_requests(rows, "gpt-5.6-luna", 1)

        self.assertEqual([item["custom_id"] for item in requests], ["meaning-000001", "meaning-000002"])
        self.assertEqual(requests[0]["body"]["model"], "gpt-5.6-luna")
        self.assertTrue(requests[0]["body"]["text"]["format"]["strict"])
        self.assertIn('"sense_id":1', requests[0]["body"]["input"][-1]["content"][0]["text"])

    def test_parse_output_rejects_fragment_and_unknown_id(self):
        output = self.write_output(
            {
                "custom_id": "meaning-000001",
                "response": {
                    "status_code": 200,
                    "body": {
                        "output_text": (
                            '{"translations":[{"sense_id":1,"meaning":"được thực hiện với ít"},'
                            '{"sense_id":99,"meaning":"nhanh"}]}'
                        )
                    },
                },
            }
        )

        rows, errors = parse_output(output, {1})

        self.assertEqual(rows, [])
        self.assertEqual(
            errors,
            [
                "meaning-000001: likely fragment for sense_id 1",
                "meaning-000001: unknown sense_id 99",
                "missing sense_id 1",
            ],
        )


if __name__ == "__main__":
    unittest.main()
