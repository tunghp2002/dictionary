import json
import tempfile
import unittest
from pathlib import Path

from scripts.batch_trans_vi_luna_function_words import (
    build_requests,
    main,
    parse_output,
    schema_required_fields,
    validate_rich_row,
)


def queue_row(sense_id: int) -> dict:
    return {
        "source_key": f"supplement:function:the{sense_id}:article",
        "word": "the",
        "pos": "article",
        "category": "article",
        "priority": sense_id,
        "description_hint": "Definite article.",
        "usage_hint": "Use before a known noun.",
        "sense_id": sense_id,
    }


def valid_row(sense_id: int = 1) -> dict:
    return {
        "sense_id": sense_id,
        "meaning": "cái, người đó",
        "description": "Definite article used before a specific noun.",
        "examples": [{"en": "The book is here.", "vi": "Cuốn sách ở đây."}],
        "collocations": ["the book", "the same"],
    }


class BatchLunaFunctionWordsTest(unittest.TestCase):
    def write_output(self, response: dict) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "output.jsonl"
        path.write_text(json.dumps(response, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def test_groups_at_most_25_and_requests_all_rich_fields(self):
        requests = build_requests([queue_row(index) for index in range(1, 27)], "gpt-5.6-luna", 25)

        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0]["body"]["model"], "gpt-5.6-luna")
        self.assertEqual(requests[0]["body"]["reasoning"]["effort"], "low")
        self.assertEqual(set(schema_required_fields(requests[0])), {
            "sense_id", "meaning", "description", "examples", "collocations"
        })

    def test_rich_row_requires_one_bilingual_example(self):
        self.assertIsNone(validate_rich_row(valid_row()))
        self.assertEqual(validate_rich_row({**valid_row(), "examples": []}), "expected one bilingual example")

    def test_rich_row_rejects_wrong_fields_and_weak_text(self):
        self.assertEqual(validate_rich_row({"sense_id": 1}), "invalid rich row fields")
        self.assertEqual(validate_rich_row({**valid_row(), "meaning": ""}), "empty meaning")
        self.assertEqual(validate_rich_row({**valid_row(), "description": "lowercase explanation"}), "description must be capitalized English sentence")
        self.assertEqual(validate_rich_row({**valid_row(), "collocations": []}), "expected one to three collocations")

    def test_rich_row_rejects_english_or_sentence_like_meanings(self):
        self.assertEqual(
            validate_rich_row({**valid_row(), "meaning": "the article"}),
            "meaning must be concise Vietnamese headword",
        )
        self.assertEqual(
            validate_rich_row({**valid_row(), "meaning": "dùng trước danh từ xác định."}),
            "meaning must be concise Vietnamese headword",
        )

    def test_rich_row_rejects_non_english_or_non_grammatical_descriptions(self):
        self.assertEqual(
            validate_rich_row({**valid_row(), "description": "Đây là mô tả ngắn."}),
            "description must be English grammatical explanation",
        )
        self.assertEqual(
            validate_rich_row({**valid_row(), "description": "A pleasant word."}),
            "description must be English grammatical explanation",
        )

    def test_rich_row_rejects_non_phrase_collocations(self):
        self.assertEqual(
            validate_rich_row({**valid_row(), "collocations": ["x"]}),
            "collocations must be natural phrases",
        )

    def test_parse_output_preserves_valid_sibling_and_marks_only_invalid_id_missing(self):
        output = self.write_output({
            "custom_id": "function-word-000001",
            "response": {"status_code": 200, "body": {"output_text": json.dumps({"translations": [
                valid_row(1), {**valid_row(2), "examples": []}
            ]}, ensure_ascii=False)}},
        })

        rows, errors = parse_output(output, {1, 2})

        self.assertEqual(rows, [valid_row(1)])
        self.assertEqual(errors, [
            "function-word-000001: expected one bilingual example for sense_id 2",
            "missing sense_id 2",
        ])

    def test_parse_partial_writes_only_invalid_id_to_retry_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue, batch, accepted, retry = (root / name for name in ("queue.jsonl", "batch.jsonl", "accepted.jsonl", "retry.jsonl"))
            source = [queue_row(1), queue_row(2)]
            queue.write_text("".join(json.dumps(row) + "\n" for row in source), encoding="utf-8")
            batch.write_text(json.dumps({
                "custom_id": "function-word-000001",
                "response": {"status_code": 200, "body": {"output_text": json.dumps({"translations": [
                    valid_row(1), {**valid_row(2), "collocations": []}
                ]})}},
            }) + "\n", encoding="utf-8")

            result = main(["parse", "--batch", str(batch), "--queue", str(queue), "--output", str(accepted), "--allow-partial", "--retry-queue", str(retry)])

            self.assertEqual(result, 1)
            self.assertEqual([json.loads(line) for line in accepted.read_text(encoding="utf-8").splitlines()], [valid_row(1)])
            self.assertEqual([json.loads(line) for line in retry.read_text(encoding="utf-8").splitlines()], [queue_row(2)])

    def test_retry_queue_excludes_previously_accepted_siblings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, accepted, retry = root / "source.jsonl", root / "accepted.jsonl", root / "retry.jsonl"
            source.write_text("".join(json.dumps(queue_row(index)) + "\n" for index in (1, 2)), encoding="utf-8")
            accepted.write_text(json.dumps(valid_row(1)) + "\n", encoding="utf-8")

            self.assertEqual(main(["retry-queue", "--source", str(source), "--accepted", str(accepted), "--output", str(retry)]), 1)
            self.assertEqual([json.loads(line) for line in retry.read_text(encoding="utf-8").splitlines()], [queue_row(2)])


if __name__ == "__main__":
    unittest.main()
