import json
import tempfile
import unittest
from pathlib import Path

from scripts.batch_trans_vi_luna_descriptions import apply_descriptions, build_requests, main, parse_output, read_jsonl, rows_from_batch_input, shard_input, write_jsonl


class BatchDescriptionsTest(unittest.TestCase):
    def test_build_requests_groups_exact_queue_rows(self):
        rows = [
            {"sense_id": 1, "word": "quick", "pos": "adj", "gloss": "moving rapidly"},
            {"sense_id": 2, "word": "quick", "pos": "adj", "gloss": "alive"},
        ]
        requests = build_requests(rows, "gpt-5.6-luna", 1)
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0]["custom_id"], "description-000001")
        self.assertEqual(requests[0]["body"]["model"], "gpt-5.6-luna")

    def test_parse_rejects_missing_or_invalid_descriptions(self):
        with tempfile.TemporaryDirectory() as name:
            output = Path(name) / "output.jsonl"
            output.write_text(json.dumps({"custom_id": "description-000001", "response": {"status_code": 200, "body": {"output_text": json.dumps({"descriptions": [{"sense_id": 1, "description": "moving rapidly"}]})}}}) + "\n", encoding="utf-8")
            rows, errors = parse_output(output, {1, 2})
        self.assertEqual(rows, [])
        self.assertIn("line 1: description must end with sentence punctuation for sense_id 1", errors)
        self.assertIn("missing sense_id 2", errors)

    def test_accepts_technical_or_quoted_sentence_endings(self):
        from scripts.batch_trans_vi_luna_descriptions import validate_description

        self.assertIsNone(validate_description("pH values above 7."))
        self.assertIsNone(validate_description("A pronunciation of \u201cafraid.\u201d"))

    def test_apply_updates_only_complete_blank_targets(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            data, queue, accepted = root / "data.jsonl", root / "queue.jsonl", root / "accepted.jsonl"
            data.write_text("\n".join(json.dumps(row) for row in (
                {"sense_id": 1, "meaning": "nhanh", "description": "", "examples": [], "collocations": []},
                {"sense_id": 2, "meaning": "sống", "description": "Existing.", "examples": [], "collocations": []},
            )) + "\n", encoding="utf-8")
            queue.write_text(json.dumps({"sense_id": 1, "word": "quick", "pos": "adj", "gloss": "moving rapidly"}) + "\n", encoding="utf-8")
            accepted.write_text(json.dumps({"sense_id": 1, "description": "Moving rapidly."}) + "\n", encoding="utf-8")
            self.assertEqual(apply_descriptions(data, accepted, queue), 1)
            rows = [json.loads(line) for line in data.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(rows[0]["description"], "Moving rapidly.")
        self.assertEqual(rows[1]["description"], "Existing.")

    def test_apply_accepts_generated_batch_input(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            data, input_path, accepted = root / "data.jsonl", root / "input.jsonl", root / "accepted.jsonl"
            data.write_text(json.dumps({"sense_id": 1, "meaning": "nhanh", "description": "", "examples": [], "collocations": []}) + "\n", encoding="utf-8")
            source = [{"sense_id": 1, "word": "quick", "pos": "adj", "gloss": "moving rapidly"}]
            write_jsonl(input_path, build_requests(source, "gpt-5.6-luna", 25))
            accepted.write_text(json.dumps({"sense_id": 1, "description": "Moving rapidly."}) + "\n", encoding="utf-8")
            self.assertEqual(apply_descriptions(data, accepted, input_path), 1)

    def test_apply_combines_distinct_accepted_files(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            data, queue, first, second = (root / path for path in ("data.jsonl", "queue.jsonl", "first.jsonl", "second.jsonl"))
            data.write_text("\n".join(json.dumps({"sense_id": sense_id, "meaning": "một", "description": "", "examples": [], "collocations": []}) for sense_id in (1, 2)) + "\n", encoding="utf-8")
            queue.write_text("\n".join(json.dumps({"sense_id": sense_id, "word": "one", "pos": "noun", "gloss": "a number"}) for sense_id in (1, 2)) + "\n", encoding="utf-8")
            first.write_text(json.dumps({"sense_id": 1, "description": "The number one."}) + "\n", encoding="utf-8")
            second.write_text(json.dumps({"sense_id": 2, "description": "The number two."}) + "\n", encoding="utf-8")
            self.assertEqual(apply_descriptions(data, [first, second], queue), 2)

    def test_partial_parse_writes_only_unaccepted_source_to_retry_queue(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            queue, batch, accepted, retry = (root / path for path in ("queue.jsonl", "batch.jsonl", "accepted.jsonl", "retry.jsonl"))
            source = [{"sense_id": sense_id, "word": "quick", "pos": "adj", "gloss": "moving rapidly"} for sense_id in (1, 2)]
            write_jsonl(queue, source)
            batch.write_text(json.dumps({"response": {"status_code": 200, "body": {"output_text": json.dumps({"descriptions": [{"sense_id": 1, "description": "Moving rapidly."}, {"sense_id": 2, "description": "\u4e2d\u6587."}]})}}}) + "\n", encoding="utf-8")
            self.assertEqual(main(["parse", "--batch", str(batch), "--queue", str(queue), "--output", str(accepted), "--allow-partial", "--retry-queue", str(retry)]), 1)
            self.assertEqual(read_jsonl(accepted), [{"sense_id": 1, "description": "Moving rapidly."}])
            self.assertEqual(read_jsonl(retry), [source[1]])

    def test_shard_keeps_requests_intact_and_below_limit(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            input_path = root / "input.jsonl"
            input_path.write_bytes(b'{"request":1}\n{"request":2}\n{"request":3}\n')
            shards = shard_input(input_path, root / "shards", 15)
            self.assertEqual([path.read_bytes() for path in shards], [b'{"request":1}\n', b'{"request":2}\n', b'{"request":3}\n'])

    def test_recovers_source_rows_from_generated_batch_input(self):
        with tempfile.TemporaryDirectory() as name:
            input_path = Path(name) / "input.jsonl"
            source = [{"sense_id": 1, "word": "quick", "pos": "adj", "gloss": "moving rapidly"}]
            write_jsonl(input_path, build_requests(source, "gpt-5.6-luna", 25))
            self.assertEqual(rows_from_batch_input(input_path), source)


if __name__ == "__main__":
    unittest.main()
