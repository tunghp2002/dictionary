import json
import tempfile
import unittest
from pathlib import Path

from scripts.batch_trans_vi_luna_meanings import (
    batch_has_downloadable_output,
    build_requests,
    main,
    parse_output,
    require_complete_coverage,
    validate_meaning,
)


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
        self.assertIn('"place" → "nơi chốn"', requests[0]["body"]["input"][0]["content"][0]["text"])
        self.assertIn("count Vietnamese words", requests[0]["body"]["input"][0]["content"][0]["text"])
        self.assertEqual(requests[0]["body"]["reasoning"]["effort"], "low")

    def test_build_requests_instructs_the_model_to_respect_fifty_character_limit(self):
        rows = [{"sense_id": 1, "word": "quick", "pos": "adjective", "gloss": ["moving fast"]}]

        request = build_requests(rows, "gpt-5.6-luna", 1)[0]

        self.assertIn("50 Vietnamese characters", request["body"]["input"][0]["content"][0]["text"])

    def test_build_requests_instructs_the_model_to_respect_twelve_word_limit(self):
        rows = [{"sense_id": 1, "word": "quick", "pos": "adjective", "gloss": ["moving fast"]}]

        request = build_requests(rows, "gpt-5.6-luna", 1)[0]

        self.assertIn("at most twelve Vietnamese words", request["body"]["input"][0]["content"][0]["text"])

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

    def test_parse_output_keeps_valid_sibling_when_one_translation_is_rejected(self):
        output = self.write_output(
            {
                "custom_id": "meaning-000001",
                "response": {
                    "status_code": 200,
                    "body": {
                        "output_text": (
                            '{"translations":[{"sense_id":1,"meaning":"nhanh"},'
                            '{"sense_id":2,"meaning":"được thực hiện với ít"}]}'
                        )
                    },
                },
            }
        )

        rows, errors = parse_output(output, {1, 2})

        self.assertEqual(rows, [{"sense_id": 1, "meaning": "nhanh"}])
        self.assertEqual(
            errors,
            ["meaning-000001: likely fragment for sense_id 2", "missing sense_id 2"],
        )

    def test_prepare_limits_pilot_and_writes_batch_jsonl(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            queue = root / "queue.jsonl"
            output = root / "pilot-input.jsonl"
            queue.write_text(
                "".join(
                    json.dumps(
                        {"sense_id": sense_id, "word": "quick", "pos": "adjective", "gloss": ["moving fast"]},
                        ensure_ascii=False,
                    )
                    + "\n"
                    for sense_id in (1, 2, 3, 4)
                ),
                encoding="utf-8",
            )

            result = main(
                [
                    "prepare",
                    "--queue",
                    str(queue),
                    "--output",
                    str(output),
                    "--limit",
                    "3",
                    "--group-size",
                    "2",
                ]
            )

            self.assertEqual(result, 2)
            self.assertEqual(len(output.read_text(encoding="utf-8").splitlines()), 2)

    def test_allows_standard_six_word_proper_name(self):
        self.assertIsNone(validate_meaning("Tổ chức Y tế Thế giới"))

    def test_allows_compact_technical_term_with_eight_words(self):
        self.assertIsNone(validate_meaning("phần mềm quản lý thông tin cá nhân"))

    def test_allows_compact_official_name_within_fifty_characters(self):
        self.assertIsNone(validate_meaning("Viện Hàn lâm Khoa học và Nghệ thuật Điện ảnh"))

    def test_allows_compact_eleven_word_official_name(self):
        self.assertIsNone(validate_meaning("Bộ Tư lệnh Điều tra Hình sự Lục quân Hoa Kỳ"))

    def test_cancelled_batch_with_output_file_is_downloadable(self):
        self.assertTrue(
            batch_has_downloadable_output(
                {"status": "cancelled", "output_file_id": "file-partial"}
            )
        )
        self.assertFalse(batch_has_downloadable_output({"status": "cancelled", "output_file_id": None}))

    def test_parse_command_writes_validated_meanings(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            queue = root / "queue.jsonl"
            batch = root / "batch.jsonl"
            output = root / "meanings.jsonl"
            queue.write_text(
                json.dumps({"sense_id": 1, "word": "quick", "pos": "adjective", "gloss": ["moving fast"]}) + "\n",
                encoding="utf-8",
            )
            batch.write_text(
                json.dumps(
                    {
                        "custom_id": "meaning-000001",
                        "response": {
                            "status_code": 200,
                            "body": {"output_text": '{"translations":[{"sense_id":1,"meaning":"nhanh"}]}'},
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = main(["parse", "--batch", str(batch), "--queue", str(queue), "--output", str(output)])

            self.assertEqual(result, 1)
            self.assertEqual(
                [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()],
                [{"sense_id": 1, "meaning": "nhanh"}],
            )

    def test_parse_command_writes_partial_result_and_retry_queue(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            queue = root / "queue.jsonl"
            batch = root / "batch.jsonl"
            output = root / "meanings.jsonl"
            retry = root / "retry.jsonl"
            source_rows = [
                {"sense_id": 1, "word": "quick", "pos": "adjective", "gloss": ["moving fast"]},
                {"sense_id": 2, "word": "do it", "pos": "verb", "gloss": ["have sexual intercourse"]},
            ]
            queue.write_text("".join(json.dumps(row) + "\n" for row in source_rows), encoding="utf-8")
            batch.write_text(
                json.dumps(
                    {
                        "custom_id": "meaning-000001",
                        "response": {
                            "status_code": 200,
                            "body": {
                                "output_text": (
                                    '{"translations":[{"sense_id":1,"meaning":"nhanh"},'
                                    '{"sense_id":2,"meaning":"được thực hiện với ít"}]}'
                                )
                            },
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = main(
                [
                    "parse",
                    "--batch",
                    str(batch),
                    "--queue",
                    str(queue),
                    "--output",
                    str(output),
                    "--allow-partial",
                    "--retry-queue",
                    str(retry),
                ]
            )

            self.assertEqual(result, 1)
            self.assertEqual([json.loads(line)["sense_id"] for line in output.read_text(encoding="utf-8").splitlines()], [1])
            self.assertEqual([json.loads(line)["sense_id"] for line in retry.read_text(encoding="utf-8").splitlines()], [2])

    def test_retry_queue_keeps_only_source_senses_not_recovered(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "source.jsonl"
            recovered = root / "recovered.jsonl"
            output = root / "retry.jsonl"
            second = {"sense_id": 2, "word": "quick", "pos": "adjective", "gloss": ["alive"]}
            source.write_text(
                json.dumps({"sense_id": 1, "word": "quick", "pos": "adjective", "gloss": ["moving fast"]})
                + "\n"
                + json.dumps(second)
                + "\n",
                encoding="utf-8",
            )
            recovered.write_text(json.dumps({"sense_id": 1, "meaning": "nhanh"}) + "\n", encoding="utf-8")

            result = main(
                [
                    "retry-queue",
                    "--source",
                    str(source),
                    "--accepted",
                    str(recovered),
                    "--output",
                    str(output),
                ]
            )

            self.assertEqual(result, 1)
            self.assertEqual([json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()], [second])

    def test_retry_queue_allows_no_recovered_files(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            source = root / "source.jsonl"
            output = root / "retry.jsonl"
            rows = [
                {"sense_id": 1, "word": "quick", "pos": "adjective", "gloss": ["moving fast"]},
                {"sense_id": 2, "word": "quick", "pos": "adjective", "gloss": ["alive"]},
            ]
            source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

            result = main(["retry-queue", "--source", str(source), "--output", str(output)])

            self.assertEqual(result, 2)
            self.assertEqual([json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()], rows)

    def test_complete_coverage_rejects_missing_target_sense(self):
        with self.assertRaisesRegex(ValueError, "missing target sense_id 2"):
            require_complete_coverage([{"sense_id": 1, "meaning": "nhanh"}], {1, 2})


if __name__ == "__main__":
    unittest.main()
