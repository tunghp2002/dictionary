import json
import tempfile
import unittest
from pathlib import Path

from scripts.merge_trans_vi_meanings import merge_meanings


class MergeTransViMeaningsTest(unittest.TestCase):
    def test_accepts_valid_compact_seven_word_term(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            data = root / "data.jsonl"
            batch = root / "batch.jsonl"
            data.write_text(
                json.dumps(
                    {
                        "sense_id": 1,
                        "meaning": "",
                        "description": "",
                        "examples": [],
                        "collocations": [],
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            batch.write_text(
                json.dumps({"sense_id": 1, "meaning": "rối loạn tăng động giảm chú ý"}) + "\n",
                encoding="utf-8",
            )

            self.assertEqual(merge_meanings([batch], data), 1)
            self.assertEqual(json.loads(data.read_text(encoding="utf-8")), {
                "sense_id": 1,
                "meaning": "rối loạn tăng động giảm chú ý",
                "description": "",
                "examples": [],
                "collocations": [],
            })


if __name__ == "__main__":
    unittest.main()
