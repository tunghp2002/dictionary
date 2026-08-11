import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_en_function_words import build_function_word_queue, load_function_words


def write_table(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )


def row(source_key: str, word: str, priority: int = 10, category: str = "pronoun") -> dict:
    return {
        "source_key": source_key,
        "word": word,
        "pos": "pronoun",
        "category": category,
        "priority": priority,
        "description_hint": "Use this word as a pronoun.",
        "usage_hint": "Use it in an ordinary sentence.",
    }


class BuildEnFunctionWordsTest(unittest.TestCase):
    def test_accepts_legacy_rows_and_tagged_informal_apostrophe_free_contraction(self):
        with tempfile.TemporaryDirectory() as temp_name:
            table_path = Path(temp_name) / "table.jsonl"
            tagged = row("supplement:function:gonna:modal", "gonna", category="modal")
            tagged["register"] = "informal"
            write_table(table_path, [row("supplement:function:i:pronoun", "I"), tagged])
            self.assertEqual(2, len(load_function_words(table_path)))

    def test_rejects_untagged_apostrophe_free_contraction(self):
        with tempfile.TemporaryDirectory() as temp_name:
            table_path = Path(temp_name) / "table.jsonl"
            write_table(table_path, [row("supplement:function:lemme:contraction", "lemme", category="contraction")])
            with self.assertRaisesRegex(ValueError, "invalid contraction spelling"):
                load_function_words(table_path)
    def test_queue_appends_ids_and_sorts_priority(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            table_path = root / "table.jsonl"
            registry_path = root / "sense-ids.tsv"
            registry_path.write_text(
                "sense_id\tsource_key\n1000000000001\told%1\n", encoding="utf-8"
            )
            write_table(
                table_path,
                [
                    row("supplement:function:you:pronoun", "you", 20),
                    row("supplement:function:i:pronoun", "I", 10),
                ],
            )

            rows, registry = build_function_word_queue(table_path, registry_path)

        self.assertEqual([item["word"] for item in rows], ["I", "you"])
        self.assertEqual(registry["old%1"], 1000000000001)
        self.assertEqual(registry["supplement:function:i:pronoun"], 1000000000002)
        self.assertEqual(registry["supplement:function:you:pronoun"], 1000000000003)

    def test_rejects_duplicate_source_key(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            table_path = root / "table.jsonl"
            registry_path = root / "sense-ids.tsv"
            registry_path.write_text("sense_id\tsource_key\n", encoding="utf-8")
            write_table(table_path, [row("supplement:function:i:pronoun", "I"), row("supplement:function:i:pronoun", "I")])

            with self.assertRaisesRegex(ValueError, "duplicate source_key"):
                build_function_word_queue(table_path, registry_path)

    def test_rejects_prohibited_category(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            table_path = root / "table.jsonl"
            registry_path = root / "sense-ids.tsv"
            registry_path.write_text("sense_id\tsource_key\n", encoding="utf-8")
            write_table(table_path, [row("supplement:function:run:verb", "run", category="verb")])

            with self.assertRaisesRegex(ValueError, "prohibited category"):
                build_function_word_queue(table_path, registry_path)


if __name__ == "__main__":
    unittest.main()
