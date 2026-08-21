import json
import tempfile
import unittest
from pathlib import Path

from scripts.batch_learning_vi import build_queue, build_requests, clean_record, normalize_learning, parse_output, validate_record


class BatchLearningViTest(unittest.TestCase):
    def test_queue_excludes_existing_and_requests_are_bounded(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); core = root / "core.jsonl"
            core.write_text("\n".join(json.dumps(row) for row in [{"word": "apply", "frequency": 2, "senses": [{"pos": "verb"}], "learning": {}}, {"word": "achieve", "frequency": 1, "senses": [{"pos": "verb"}]}, {"word": "Achieve", "frequency": 3, "senses": [{"pos": "noun"}]}]) + "\n", encoding="utf-8")
            queue = build_queue(core, 10)
            self.assertEqual(queue, [{"word": "achieve", "pos": ["verb"]}])
            self.assertEqual(build_queue(core, 10, {"achieve"}), [])
            requests = build_requests(queue, "gpt-5.6-luna", 10)
            self.assertEqual(len(requests), 1)
            family = requests[0]["body"]["text"]["format"]["schema"]["properties"]["records"]["items"]["properties"]["word_family"]["items"]
            self.assertEqual(family["required"], ["word"])
            self.assertEqual(set(family["properties"]), {"word"})

    def test_parse_accepts_only_complete_known_records(self):
        queue = [{"word": "achieve", "pos": ["verb"]}]
        record = {"word": "achieve", "grammar_patterns": [{"pattern": "achieve a goal", "vi": "đạt mục tiêu"}], "word_family": [], "usage_notes": [], "confusables": []}
        with tempfile.TemporaryDirectory() as name:
            batch = Path(name) / "batch.jsonl"
            batch.write_text(json.dumps({"response": {"status_code": 200, "body": {"output_text": json.dumps({"records": [record]})}}}) + "\n", encoding="utf-8")
            rows, errors = parse_output(batch, queue)
        self.assertEqual(rows, [record]); self.assertEqual(errors, [])

    def test_normalize_word_family_keeps_only_distinct_core_headwords(self):
        row = {"word": "increase", "grammar_patterns": [], "word_family": [{"word": "increase", "pos": "noun", "meaning": "sự tăng"}, {"word": "increasing", "pos": "adj", "meaning": "ngày càng tăng"}, {"word": "lookable", "pos": "adj", "meaning": "có thể nhìn"}], "usage_notes": [], "confusables": []}
        self.assertEqual(
            normalize_learning(row, {"increase": "increase", "increasing": "increasing"}),
            {"grammar_patterns": [], "word_family": [{"word": "increasing"}], "usage_notes": [], "confusables": []},
        )

    def test_clean_record_discards_only_invalid_nested_items(self):
        row = {"word": "mutual", "grammar_patterns": [{"pattern": "mutual trust", "vi": ""}], "word_family": [], "usage_notes": [{"en": "shared by two people", "vi": "được hai người cùng chia sẻ"}], "confusables": []}
        cleaned = clean_record(row)
        self.assertEqual(cleaned["grammar_patterns"], [])
        self.assertIsNone(validate_record(cleaned, {"mutual"}))


if __name__ == "__main__":
    unittest.main()
