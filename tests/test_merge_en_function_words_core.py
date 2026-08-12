import json
import hashlib
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from scripts.build_core_en import load_id_registry
from scripts.merge_en_function_words_core import merge_function_words_into_core


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def function_word(source_key: str, word: str, pos: str, priority: int, *, register: str | None = None) -> dict:
    row = {
        "source_key": source_key,
        "word": word,
        "pos": pos,
        "category": pos,
        "priority": priority,
        "description_hint": "A test description.",
        "usage_hint": "A test usage hint.",
    }
    if register is not None:
        row["register"] = register
    return row


def find_word(path: Path, word: str) -> dict:
    return next(row for row in read_jsonl(path) if row["word"] == word)


class MergeEnFunctionWordsCoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.core = self.root / "data.jsonl"
        self.forms = self.root / "function-words.jsonl"
        self.registry = self.root / "sense-ids.tsv"
        self.meta = self.root / "meta.json"

    def tearDown(self):
        self.temp.cleanup()

    def write_registry(self, rows: list[tuple[int, str]]) -> None:
        self.registry.write_text(
            "sense_id\tsource_key\n" + "".join(f"{sense_id}\t{key}\n" for sense_id, key in rows),
            encoding="utf-8",
        )

    def write_meta(self) -> None:
        self.meta.write_text(
            json.dumps({
                "records": 0, "senses": 0, "reserved_sense_ids": 0,
                "with_frequency": 0, "output": {"path": "data.jsonl", "sha256": "old", "bytes": 0},
                "preserve": {"nested": ["value"]},
            }, indent=2) + "\n",
            encoding="utf-8",
        )

    def test_informal_and_standard_senses_are_normalized_and_metadata_refreshes(self):
        write_jsonl(self.core, [
            {"word": "gonna", "frequency": 8, "senses": [{"id": 1000000000001, "pos": "noun"}]},
            {"word": "is", "frequency": 9, "senses": [{"id": 1000000000002, "pos": "verb"}]},
        ])
        write_jsonl(self.forms, [
            function_word("supplement:function:gonna:modal", "gonna", "modal", 6, register="informal"),
            function_word("supplement:function:is:auxiliary", "is", "auxiliary", 1),
        ])
        self.write_registry([
            (1000000000001, "old:gonna"), (1000000000002, "old:is"),
            (1000000000003, "supplement:function:gonna:modal"),
            (1000000000004, "supplement:function:is:auxiliary"),
        ])
        self.write_meta()

        self.assertEqual(merge_function_words_into_core(self.core, self.forms, self.registry, self.meta), 2)

        gonna = find_word(self.core, "gonna")
        self.assertEqual(
            next(sense for sense in gonna["senses"] if sense["id"] == 1000000000003),
            {"id": 1000000000003, "pos": "modal", "tags": {"register": ["informal"]}},
        )
        is_record = find_word(self.core, "is")
        self.assertEqual(
            next(sense for sense in is_record["senses"] if sense["id"] == 1000000000004),
            {"id": 1000000000004, "pos": "auxiliary"},
        )
        metadata = json.loads(self.meta.read_text(encoding="utf-8"))
        payload = self.core.read_bytes()
        self.assertEqual(metadata["records"], 2)
        self.assertEqual(metadata["senses"], 4)
        self.assertEqual(metadata["reserved_sense_ids"], 4)
        self.assertEqual(metadata["with_frequency"], 2)
        self.assertEqual(metadata["output"]["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(metadata["output"]["bytes"], len(payload))
        self.assertEqual(metadata["preserve"], {"nested": ["value"]})

    def test_rerun_normalizes_target_tag_and_preserves_unrelated_tagged_sense(self):
        write_jsonl(self.core, [{
            "word": "gonna", "frequency": 6,
            "senses": [
                {"id": 1000000000001, "pos": "noun", "tags": {"register": ["archaic"]}},
                {"id": 1000000000003, "pos": "wrong", "tags": {"register": ["standard"]}},
            ],
        }])
        write_jsonl(self.forms, [
            function_word("supplement:function:gonna:modal", "gonna", "modal", 6, register="informal"),
        ])
        self.write_registry([
            (1000000000001, "old:gonna"),
            (1000000000003, "supplement:function:gonna:modal"),
        ])

        merge_function_words_into_core(self.core, self.forms, self.registry)
        first = self.core.read_bytes()
        merge_function_words_into_core(self.core, self.forms, self.registry)

        senses = find_word(self.core, "gonna")["senses"]
        self.assertEqual(senses[0], {"id": 1000000000001, "pos": "noun", "tags": {"register": ["archaic"]}})
        self.assertEqual(senses[1], {"id": 1000000000003, "pos": "modal", "tags": {"register": ["informal"]}})
        self.assertEqual(self.core.read_bytes(), first)

    def test_existing_word_gets_new_sense_and_priority(self):
        write_jsonl(self.core, [{"word": "I", "frequency": 5, "senses": [{"id": 1000000000001, "pos": "noun"}]}])
        write_jsonl(self.forms, [function_word("supplement:function:i:pronoun", "I", "pronoun", 1)])
        self.write_registry([(1000000000001, "old:i"), (1000000000003, "supplement:function:i:pronoun")])

        merge_function_words_into_core(self.core, self.forms, self.registry)
        record = find_word(self.core, "I")
        self.assertEqual({sense["id"] for sense in record["senses"]}, {1000000000001, 1000000000003})
        self.assertEqual(record["frequency"], 1)

    def test_missing_word_is_inserted_alphabetically_and_merge_is_idempotent(self):
        write_jsonl(self.core, [
            {"word": "I", "frequency": 5, "senses": [{"id": 1000000000001, "pos": "noun"}]},
            {"word": "zoo", "frequency": 9, "senses": [{"id": 1000000000004, "pos": "noun"}]},
        ])
        write_jsonl(self.forms, [
            function_word("supplement:function:a:article", "a", "article", 2),
            function_word("supplement:function:i:pronoun", "I", "pronoun", 1),
        ])
        self.write_registry([
            (1000000000001, "old:i"),
            (1000000000002, "supplement:function:a:article"),
            (1000000000003, "supplement:function:i:pronoun"),
            (1000000000004, "old:zoo"),
        ])

        merge_function_words_into_core(self.core, self.forms, self.registry)
        first = read_jsonl(self.core)
        merge_function_words_into_core(self.core, self.forms, self.registry)
        self.assertEqual(read_jsonl(self.core), first)
        self.assertEqual([row["word"] for row in first], ["a", "I", "zoo"])

    def test_missing_registry_and_conflicting_id_are_rejected(self):
        write_jsonl(self.core, [{"word": "zoo", "senses": [{"id": 1000000000001, "pos": "noun"}]}])
        write_jsonl(self.forms, [function_word("supplement:function:i:pronoun", "I", "pronoun", 1)])
        empty_registry = self.root / "empty.tsv"
        empty_registry.write_text("sense_id\tsource_key\n", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "missing registry"):
            merge_function_words_into_core(self.core, self.forms, empty_registry)

        self.write_registry([(1000000000001, "supplement:function:i:pronoun")])
        with self.assertRaisesRegex(ValueError, "different word"):
            merge_function_words_into_core(self.core, self.forms, self.registry)

    def test_real_supplemental_senses_use_schema_pos_categories(self):
        root = Path(__file__).parents[1]
        schema = json.loads((root / "packs/en/core/schema.json").read_text(encoding="utf-8"))
        allowed = set(schema["$defs"]["sense"]["properties"]["pos"]["enum"])
        registry = load_id_registry(root / "packs/en/core/sense-ids.tsv")
        expected = {
            registry[row["source_key"]]: row
            for row in read_jsonl(root / "packs/en/core/function-words.jsonl")
        }
        self.assertEqual(len(expected), 327)
        informal_ids = {
            numeric_id for numeric_id, row in expected.items()
            if row.get("register") == "informal"
        }
        self.assertEqual(len(informal_ids), 8)
        occurrences = Counter()
        for record in read_jsonl(root / "packs/en/core/data.jsonl"):
            for sense in record["senses"]:
                if sense["id"] not in expected:
                    continue
                occurrences[sense["id"]] += 1
                self.assertEqual(sense["pos"], expected[sense["id"]]["category"])
                if sense["id"] in informal_ids:
                    self.assertEqual(sense.get("tags", {}).get("register"), ["informal"])
                else:
                    self.assertNotIn("tags", sense)
        self.assertEqual(set(occurrences), set(expected))
        self.assertTrue(all(count == 1 for count in occurrences.values()))
        self.assertTrue(all(row["category"] in allowed for row in expected.values()))

    def test_checked_in_metadata_summary_matches_artifacts(self):
        root = Path(__file__).parents[1]
        metadata = json.loads((root / "packs/en/core/meta.json").read_text(encoding="utf-8"))
        records = read_jsonl(root / "packs/en/core/data.jsonl")

        self.assertEqual(metadata["records"], len(records))
        self.assertEqual(metadata["senses"], sum(len(record["senses"]) for record in records))
        self.assertEqual(metadata["reserved_sense_ids"], len(load_id_registry(root / "packs/en/core/sense-ids.tsv")))
        self.assertEqual(metadata["with_frequency"], sum("frequency" in record for record in records))


if __name__ == "__main__":
    unittest.main()
