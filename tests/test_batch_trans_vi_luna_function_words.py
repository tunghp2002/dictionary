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


def where_source() -> dict:
    return {
        **queue_row(1),
        "source_key": "supplement:function:where:adv",
        "word": "where",
        "pos": "adv",
        "category": "adv",
        "description_hint": "Interrogative or relative adverb asking about place.",
        "usage_hint": "Use it in a question or relative clause about location.",
    }


def gonna_source() -> dict:
    return {
        **queue_row(1),
        "source_key": "supplement:function:gonna:modal",
        "word": "gonna",
        "pos": "verb",
        "category": "modal",
        "description_hint": "Informal spoken reduction of going to before a verb.",
        "usage_hint": "Use it only in informal speech or dialogue.",
        "register": "informal",
    }


class BatchLunaFunctionWordsTest(unittest.TestCase):
    def write_output(self, response: dict) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "output.jsonl"
        path.write_text(json.dumps(response, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def parse_one_with_source(self, row: dict, source: dict) -> tuple[list[dict], list[str]]:
        return parse_output(self.write_output({
            "custom_id": "function-word-000001",
            "response": {"status_code": 200, "body": {"output_text": json.dumps({"translations": [row]})}},
        }), {source["sense_id"]: source})

    def test_groups_at_most_25_and_requests_all_rich_fields(self):
        requests = build_requests([queue_row(index) for index in range(1, 27)], "gpt-5.6-luna", 25)

        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0]["body"]["model"], "gpt-5.6-luna")
        self.assertEqual(requests[0]["body"]["reasoning"]["effort"], "low")
        self.assertEqual(set(schema_required_fields(requests[0])), {
            "sense_id", "meaning", "description", "examples", "collocations"
        })

    def test_requests_preserve_optional_informal_register(self):
        request = build_requests([gonna_source()], "gpt-5.6-luna", 25)[0]

        self.assertEqual(request["body"]["input"][1]["content"][0]["text"].count('"register":"informal"'), 1)

    def test_parse_accepts_role_specific_adverb_description(self):
        row = {**valid_row(), "meaning": "ở đâu", "description": "Adverb asking about or referring to a place.", "collocations": ["where are you", "from where"]}

        rows, errors = self.parse_one_with_source(row, where_source())

        self.assertEqual(rows, [row])
        self.assertEqual(errors, [])

    def test_parse_requires_informal_wording_for_informal_source(self):
        row = {**valid_row(), "meaning": "sắp", "description": "Modal spoken reduction of going to before a verb.", "collocations": ["gonna leave", "gonna call"]}

        rows, errors = self.parse_one_with_source(row, gonna_source())

        self.assertEqual(rows, [])
        self.assertTrue(any("description must state informal register for sense_id 1" in error for error in errors))

        informal_row = {**row, "description": "Informal modal spoken reduction of going to before a verb."}
        rows, errors = self.parse_one_with_source(informal_row, gonna_source())
        self.assertEqual(rows, [informal_row])
        self.assertEqual(errors, [])

    def test_rich_row_requires_one_bilingual_example(self):
        self.assertIsNone(validate_rich_row(valid_row()))
        self.assertEqual(validate_rich_row({**valid_row(), "examples": []}), "expected one bilingual example")

    def test_rich_row_rejects_wrong_fields_and_weak_text(self):
        self.assertEqual(validate_rich_row({"sense_id": 1}), "invalid rich row fields")
        self.assertEqual(validate_rich_row({**valid_row(), "meaning": ""}), "empty meaning")
        self.assertEqual(validate_rich_row({**valid_row(), "description": "lowercase explanation"}), "description must be capitalized English sentence")
        self.assertEqual(validate_rich_row({**valid_row(), "collocations": []}), "expected one to three collocations")

    def test_rich_row_rejects_sentence_like_meanings(self):
        self.assertEqual(
            validate_rich_row({**valid_row(), "meaning": "dùng trước danh từ xác định."}),
            "meaning must be concise Vietnamese headword",
        )

    def test_rich_row_accepts_a_quoted_english_form_in_a_concise_vietnamese_meaning(self):
        self.assertIsNone(validate_rich_row({**valid_row(), "meaning": "trợ động từ “am”"}))

    def test_rich_row_rejects_vowelless_meaning_garbage(self):
        self.assertEqual(
            validate_rich_row({**valid_row(), "meaning": "xđ"}),
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

    def test_rich_row_leaves_latin_word_semantics_to_final_audit(self):
        self.assertIsNone(validate_rich_row({**valid_row(), "meaning": "café"}))

    def test_rich_row_rejects_one_word_description(self):
        self.assertEqual(
            validate_rich_row({**valid_row(), "description": "Article."}),
            "description must be English grammatical explanation",
        )

    def test_rich_row_rejects_vowelless_collocation(self):
        self.assertEqual(
            validate_rich_row({**valid_row(), "collocations": ["zz zz"]}),
            "collocations must be natural phrases",
        )

    def test_rich_row_accepts_expected_function_word_shapes(self):
        self.assertIsNone(validate_rich_row({
            **valid_row(),
            "meaning": "cho",
            "description": "Preposition used before a recipient.",
            "collocations": ["give to", "for you"],
        }))

    def test_parse_accepts_short_vietnamese_meaning_without_a_lexical_whitelist(self):
        source = {
            **queue_row(1),
            "source_key": "supplement:function:other:determiner",
            "word": "other",
            "pos": "determiner",
            "category": "determiner",
            "description_hint": "Refer to a different person or thing.",
            "usage_hint": "Place before a noun.",
        }
        row = {
            **valid_row(),
            "meaning": "khác",
            "description": "Determiner selecting an alternative noun.",
            "collocations": ["other people", "other things"],
        }

        rows, errors = self.parse_one_with_source(row, source)

        self.assertEqual(rows, [row])
        self.assertEqual(errors, [])

    def test_parse_rejects_pos_label_description_with_source_context(self):
        rows, errors = self.parse_one_with_source({**valid_row(), "description": "A noun word."}, queue_row(1))

        self.assertEqual(rows, [])
        self.assertTrue(any("description must match source grammatical category for sense_id 1" in error for error in errors))

    def test_parse_rejects_generic_description_despite_matching_category(self):
        rows, errors = self.parse_one_with_source({**valid_row(), "description": "An article word."}, queue_row(1))

        self.assertEqual(rows, [])
        self.assertTrue(any("description must be sufficiently explanatory for sense_id 1" in error for error in errors))

    def test_parse_rejects_collocation_unrelated_to_source_form(self):
        rows, errors = self.parse_one_with_source({**valid_row(), "collocations": ["aa bb"]}, queue_row(1))

        self.assertEqual(rows, [])
        self.assertTrue(any("collocations must include source form for sense_id 1" in error for error in errors))

    def test_parse_rejects_garbage_after_source_form_in_collocation(self):
        rows, errors = self.parse_one_with_source({**valid_row(), "collocations": ["the aa"]}, queue_row(1))

        self.assertEqual(rows, [])
        self.assertTrue(any("collocations must include usable context for sense_id 1" in error for error in errors))

    def test_parse_accepts_single_letter_source_form_in_collocation(self):
        source = {
            **queue_row(1),
            "source_key": "supplement:function:a:article",
            "word": "a",
            "description_hint": "Introduce one non-specific singular countable noun.",
            "usage_hint": "Place before a consonant-sound noun.",
        }
        row = {
            **valid_row(),
            "description": "Article placed before a non-specific countable noun.",
            "collocations": ["a book", "a few"],
        }

        rows, errors = self.parse_one_with_source(row, source)

        self.assertEqual(rows, [row])
        self.assertEqual(errors, [])

    def test_parse_accepts_single_letter_context_around_source_form(self):
        source = {
            **queue_row(1),
            "source_key": "supplement:function:little:quantifier",
            "word": "little",
            "pos": "quantifier",
            "category": "quantifier",
            "description_hint": "Refer to a small amount.",
            "usage_hint": "Use before uncountable nouns.",
        }
        row = {
            **valid_row(),
            "meaning": "ít",
            "description": "Quantifier referring to a small amount.",
            "collocations": ["a little"],
        }

        rows, errors = self.parse_one_with_source(row, source)

        self.assertEqual(rows, [row])
        self.assertEqual(errors, [])

    def test_parse_accepts_valid_contraction_with_source_context(self):
        source = {
            **queue_row(1),
            "source_key": "supplement:function:will-not:contraction",
            "word": "won't",
            "category": "contraction",
            "pos": "contraction",
            "description_hint": "Contract will not.",
            "usage_hint": "Use in informal speech and writing.",
        }
        row = {**valid_row(), "meaning": "sẽ không", "description": "Contraction of “will not” — a negative modal form.", "examples": [{"en": "I won't wait.", "vi": "Tôi sẽ không chờ."}], "collocations": ["won't wait", "won't help"]}

        rows, errors = self.parse_one_with_source(row, source)

        self.assertEqual(rows, [row])
        self.assertEqual(errors, [])

    def test_parse_output_preserves_valid_sibling_and_marks_only_invalid_id_missing(self):
        output = self.write_output({
            "custom_id": "function-word-000001",
            "response": {"status_code": 200, "body": {"output_text": json.dumps({"translations": [
                valid_row(1), {**valid_row(2), "examples": []}
            ]}, ensure_ascii=False)}},
        })

        rows, errors = parse_output(output, {1: queue_row(1), 2: queue_row(2)})

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
