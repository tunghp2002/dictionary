import json
import tempfile
import unittest
from pathlib import Path

from scripts.batch_trans_vi_examples_collocations import (
    apply_fields,
    build_queue,
    build_requests,
    fallback_rows,
    parse_output,
    validate_rich_fields,
)


def source_row(sense_id=1):
    return {
        "sense_id": sense_id,
        "word": "bird",
        "pos": "noun",
        "meaning": "chim",
        "description": "A warm-blooded egg-laying vertebrate with feathers and wings.",
    }


def rich_row(sense_id=1):
    return {
        "sense_id": sense_id,
        "examples": [{"en": "A bird sings.", "vi": "Một con chim hót."}],
        "collocations": ["small bird"],
    }


class BatchTransViExamplesCollocationsTest(unittest.TestCase):
    def test_checked_in_rich_fields_pass_quality_gate(self):
        root = Path(__file__).resolve().parents[1]

        invalid = build_queue(
            root / "packs/en/core/data.jsonl",
            root / "packs/en/trans-vi/data.jsonl",
            include_invalid=True,
        )

        self.assertEqual(invalid, [])

    def test_build_requests_has_compact_rich_schema(self):
        requests = build_requests([source_row(index) for index in range(1, 27)], "gpt-5-nano", 25)

        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0]["body"]["model"], "gpt-5-nano")
        self.assertEqual(requests[0]["body"]["max_output_tokens"], 3000)
        self.assertEqual(requests[0]["body"]["reasoning"]["effort"], "minimal")
        required = requests[0]["body"]["text"]["format"]["schema"]["properties"]["records"]["items"]["required"]
        self.assertEqual(set(required), {"sense_id", "examples", "collocations"})

        luna = build_requests([source_row()], "gpt-5.6-luna", 1)
        self.assertEqual(luna[0]["body"]["reasoning"]["effort"], "none")
        luna_low = build_requests([source_row()], "gpt-5.6-luna", 1, "low")
        self.assertEqual(luna_low[0]["body"]["reasoning"]["effort"], "low")

    def test_parse_accepts_valid_record(self):
        response = {
            "response": {"status_code": 200, "body": {"output_text": json.dumps({"records": [rich_row()]})}}
        }
        with tempfile.TemporaryDirectory() as temp_name:
            output = Path(temp_name) / "output.jsonl"
            output.write_text(json.dumps(response) + "\n", encoding="utf-8")
            rows, errors = parse_output(output, {1: source_row()})

        self.assertEqual(rows, [rich_row()])
        self.assertEqual(errors, [])

    def test_validator_requires_source_form_in_collocation(self):
        self.assertEqual(
            validate_rich_fields({**rich_row(), "collocations": ["small animal"]}, source_row()),
            "collocation must include source form",
        )

    def test_validator_rejects_untranslated_examples_and_pos_labels(self):
        row = rich_row()
        row["examples"] = [{"en": "A bird sings.", "vi": "A bird sings."}]
        self.assertEqual(validate_rich_fields(row, source_row()), "Vietnamese example duplicates English")
        row["examples"] = [{"en": "A bird sings.", "vi": "Một con chim hót."}]
        for collocation in ("bird noun", "bird_usage", "bird phrase?"):
            row["collocations"] = [collocation]
            self.assertIsNotNone(validate_rich_fields(row, source_row()))

        linguistic = {**source_row(), "word": "attributive", "description": "Used before a noun in grammar."}
        row["collocations"] = ["attributive adjective"]
        self.assertIsNone(validate_rich_fields(row, linguistic))

        adverb = {**source_row(), "word": "jocular", "pos": "adv"}
        row["collocations"] = ["jocular adv manner"]
        self.assertEqual(validate_rich_fields(row, adverb), "part-of-speech label in collocation")

        artifact = {**source_row(), "word": "sweet", "pos": "adj", "description": "Pleasing to the senses."}
        row["collocations"] = ["sweet Pleasing to the senses"]
        self.assertEqual(validate_rich_fields(row, artifact), "description pasted into collocation")
        row["collocations"] = ["traffic buôn bán phi pháp"]
        self.assertIsNotNone(validate_rich_fields(row, artifact))

        row["collocations"] = ["birds in flight"]
        self.assertIsNone(validate_rich_fields(row, source_row()))

        slash = {**source_row(), "word": "TCP/IP"}
        row["collocations"] = ["TCP/IP protocols"]
        self.assertIsNone(validate_rich_fields(row, slash))
        means = {**source_row(), "word": "by all means"}
        row["collocations"] = ["by all means"]
        self.assertIsNone(validate_rich_fields(row, means))

    def test_validator_accepts_numeric_and_rejects_shortened_multiword_forms(self):
        numeric_source = {**source_row(), "word": ".22"}
        self.assertIsNone(validate_rich_fields({**rich_row(), "collocations": [".22 pistol"]}, numeric_source))
        numeric_source["word"] = "0"
        self.assertIsNone(validate_rich_fields({**rich_row(), "collocations": ["zero value"]}, numeric_source))
        multiword_source = {**source_row(), "word": "allspice tree"}
        self.assertEqual(
            validate_rich_fields({**rich_row(), "collocations": ["allspice berries"]}, multiword_source),
            "collocation must include source form",
        )

    def test_apply_replaces_only_empty_rich_fields(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            data, queue, accepted = root / "data.jsonl", root / "queue.jsonl", root / "accepted.jsonl"
            data.write_text(json.dumps({**source_row(), "examples": [], "collocations": []}) + "\n", encoding="utf-8")
            queue.write_text(json.dumps(source_row()) + "\n", encoding="utf-8")
            accepted.write_text(json.dumps(rich_row()) + "\n", encoding="utf-8")

            self.assertEqual(apply_fields(data, [accepted], queue), 1)
            self.assertEqual(json.loads(data.read_text(encoding="utf-8")), {**source_row(), **rich_row()})

    def test_apply_can_safely_merge_a_valid_subset(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            data, queue, accepted = root / "data.jsonl", root / "queue.jsonl", root / "accepted.jsonl"
            data.write_text("".join(json.dumps({**source_row(sense_id), "examples": [], "collocations": []}) + "\n" for sense_id in (1, 2)), encoding="utf-8")
            queue.write_text("".join(json.dumps(source_row(sense_id)) + "\n" for sense_id in (1, 2)), encoding="utf-8")
            accepted.write_text(json.dumps(rich_row()) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "do not cover"):
                apply_fields(data, [accepted], queue)
            self.assertEqual(apply_fields(data, [accepted], queue, allow_partial=True), 1)

    def test_apply_replaces_only_invalid_existing_fields_when_requested(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            data, queue, accepted = root / "data.jsonl", root / "queue.jsonl", root / "accepted.jsonl"
            invalid = {**source_row(), "examples": [{"en": "A bird sings.", "vi": "A bird sings."}], "collocations": ["bird noun"]}
            data.write_text(json.dumps(invalid) + "\n", encoding="utf-8")
            queue.write_text(json.dumps(source_row()) + "\n", encoding="utf-8")
            accepted.write_text(json.dumps(rich_row()) + "\n", encoding="utf-8")

            self.assertEqual(apply_fields(data, [accepted], queue, replace_invalid=True), 1)
            self.assertEqual(json.loads(data.read_text(encoding="utf-8")), {**source_row(), **rich_row()})

            with self.assertRaisesRegex(ValueError, "refusing to replace valid"):
                apply_fields(data, [accepted], queue, replace_invalid=True)

    def test_fallback_keeps_only_fully_valid_model_rows(self):
        source = {**source_row(), "word": "allspice tree"}
        response = {"response": {"body": {"output_text": json.dumps({"records": [{
            **rich_row(), "examples": [{"en": "The allspice tree grows well.", "vi": "Cây tiêu Jamaica phát triển tốt."}],
            "collocations": ["allspice berries"],
        }]})}}}
        with tempfile.TemporaryDirectory() as temp_name:
            output = Path(temp_name) / "output.jsonl"
            output.write_text(json.dumps(response) + "\n", encoding="utf-8")
            rows = fallback_rows(output, {1: source})

        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
