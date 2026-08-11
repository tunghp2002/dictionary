import json
import tempfile
import unittest
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


def function_word(source_key: str, word: str, pos: str, priority: int) -> dict:
    return {
        "source_key": source_key,
        "word": word,
        "pos": pos,
        "category": pos,
        "priority": priority,
        "description_hint": "A test description.",
        "usage_hint": "A test usage hint.",
    }


def find_word(path: Path, word: str) -> dict:
    return next(row for row in read_jsonl(path) if row["word"] == word)


class MergeEnFunctionWordsCoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.core = self.root / "data.jsonl"
        self.forms = self.root / "function-words.jsonl"
        self.registry = self.root / "sense-ids.tsv"

    def tearDown(self):
        self.temp.cleanup()

    def write_registry(self, rows: list[tuple[int, str]]) -> None:
        self.registry.write_text(
            "sense_id\tsource_key\n" + "".join(f"{sense_id}\t{key}\n" for sense_id, key in rows),
            encoding="utf-8",
        )

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
        emitted = {
            sense["id"]: sense["pos"]
            for record in read_jsonl(root / "packs/en/core/data.jsonl")
            for sense in record["senses"]
        }
        for row in read_jsonl(root / "packs/en/core/function-words.jsonl"):
            self.assertEqual(emitted[registry[row["source_key"]]], row["category"])
            self.assertIn(row["category"], allowed)


if __name__ == "__main__":
    unittest.main()
