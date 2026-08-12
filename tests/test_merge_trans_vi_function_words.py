import json
import tempfile
import unittest
from pathlib import Path

from scripts.merge_trans_vi_function_words import merge_function_words


def rich_row(sense_id=1000000000002):
    return {
        "sense_id": sense_id,
        "meaning": "cái đó",
        "description": "Article used before a specific noun.",
        "examples": [{"en": "The book is here.", "vi": "Cuốn sách ở đây."}],
        "collocations": ["the book"],
    }


class MergeTransViFunctionWordsTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.registry = self.root / "sense-ids.tsv"
        self.data = self.root / "data.jsonl"
        self.registry.write_text(
            "sense_id\tsource_key\n"
            "1000000000001\toewn:one\n"
            "1000000000002\tsupplement:function:the:article\n",
            encoding="utf-8",
        )
        self.data.write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in (
                {"sense_id": 1000000000001, "meaning": "một", "description": "Old OEWN detail.", "examples": [{"en": "One.", "vi": "Một."}], "collocations": ["one day"]},
                {"sense_id": 1000000000002, "meaning": "", "description": "", "examples": [], "collocations": []},
            )),
            encoding="utf-8",
        )

    def test_merge_rejects_unknown_or_incomplete_id(self):
        with self.assertRaisesRegex(ValueError, "unknown supplement sense_id"):
            merge_function_words(self.data, [rich_row(999)], self.registry)
        with self.assertRaisesRegex(ValueError, "incomplete rich row"):
            merge_function_words(self.data, [{**rich_row(), "examples": []}], self.registry)

    def test_merge_requires_exactly_one_row_per_supplement_and_preserves_full_row(self):
        with self.assertRaisesRegex(ValueError, "missing supplement sense_id"):
            merge_function_words(self.data, [], self.registry)
        with self.assertRaisesRegex(ValueError, "duplicate supplement sense_id"):
            merge_function_words(self.data, [rich_row(), rich_row()], self.registry)

        self.assertEqual(merge_function_words(self.data, [rich_row()], self.registry), 1)
        rows = [json.loads(line) for line in self.data.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(rows[1], rich_row())
        self.assertEqual(rows[0]["description"], "Old OEWN detail.")

    def test_merge_preserves_legacy_long_meaning_but_rejects_new_long_meaning(self):
        legacy = {**rich_row(), "meaning": "một nghĩa tiếng Việt dài hơn năm từ"}
        self.assertEqual(merge_function_words(self.data, [legacy], self.registry), 1)


    def test_expansion_manifest_enforces_five_word_meaning_while_legacy_is_preserved(self):
        self.registry.write_text(self.registry.read_text(encoding="utf-8") + "1000000000003\tsupplement:function:new:article\n", encoding="utf-8")
        (self.root / "function-words-expansion.jsonl").write_text(json.dumps({"source_key": "supplement:function:new:article", "word": "new", "pos": "article", "category": "article", "priority": 1, "description_hint": "New article.", "usage_hint": "Use new."}) + "\n", encoding="utf-8")
        legacy = {**rich_row(), "meaning": "mot nghia tieng Viet dai hon nam tu"}
        expansion = {**rich_row(1000000000003), "meaning": "mot nghia tieng Viet qua dai day"}
        with self.assertRaisesRegex(ValueError, "meaning must be concise"):
            merge_function_words(self.data, [legacy, expansion], self.registry)
        expansion["meaning"] = "moi"
        self.assertEqual(merge_function_words(self.data, [legacy, expansion], self.registry), 2)


if __name__ == "__main__":
    unittest.main()
