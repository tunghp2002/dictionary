import tempfile
import unittest
import json
import subprocess
from pathlib import Path

import yaml

from scripts.build_core_en import (
    LANGUAGE_NAMESPACE,
    LOCAL_ID_BASE,
    MAX_SAFE_INTEGER,
    add_frequency_ranks,
    assign_sense_ids,
    finalize_records,
    grammar_from_subcats,
    load_entries,
    file_sha256,
    sense_id,
)


class BuildCoreEnTest(unittest.TestCase):
    def test_core_data_is_configured_for_lf_checkout(self):
        root = Path(__file__).parents[1]
        result = subprocess.run(
            ["git", "check-attr", "eol", "--", "packs/en/core/data.jsonl"],
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(
            result.stdout.strip(),
            "packs/en/core/data.jsonl: eol: lf",
        )

    def test_builds_schema_with_stable_safe_integer_ids(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            entries = root / "entries"
            entries.mkdir()
            (entries / "entries-h.yaml").write_text(
                yaml.safe_dump(
                    {
                        "heavy": {
                            "a": {
                                "pronunciation": [{"value": "ˈhɛ.vi"}],
                                "sense": [
                                    {"id": "heavy%3:00:01::", "synset": "01188475-a"},
                                    {"id": "heavy%3:00:03::", "synset": "01194226-a"},
                                ],
                            }
                        }
                    },
                    sort_keys=False,
                    allow_unicode=True,
                ),
                encoding="utf-8",
            )
            records, source_keys = load_entries(entries)
            registry = {}
            assign_sense_ids(records, registry)
            add_frequency_ranks(records, lambda _: 5.0)
            finalize_records(records)

        self.assertEqual(records[0]["word"], "heavy")
        self.assertEqual(records[0]["ipa"], "/ˈhɛ.vi/")
        self.assertEqual(records[0]["frequency"], 1)
        self.assertEqual(len(records[0]["senses"]), 2)
        self.assertEqual(
            [sense["id"] for sense in records[0]["senses"]],
            [LOCAL_ID_BASE + 1, LOCAL_ID_BASE + 2],
        )
        self.assertEqual(set(source_keys), set(registry))
        self.assertTrue(all(0 < value <= MAX_SAFE_INTEGER for value in registry.values()))
        self.assertEqual(sense_id(1), LANGUAGE_NAMESPACE * LOCAL_ID_BASE + 1)
        self.assertNotIn("meaning", records[0])
        self.assertNotIn("vi", records[0])

    def test_registry_keeps_old_ids_and_sorts_them(self):
        records = [
            {
                "word": "heavy",
                "senses": [
                    {"_source_key": "newer", "pos": "adj"},
                    {"_source_key": "older", "pos": "adj"},
                ],
            }
        ]
        registry = {
            "newer": sense_id(9),
            "older": sense_id(3),
            "deleted-but-reserved": sense_id(10),
        }
        assign_sense_ids(records, registry)
        self.assertEqual(
            [sense["id"] for sense in records[0]["senses"]],
            [sense_id(3), sense_id(9)],
        )
        self.assertEqual(registry["deleted-but-reserved"], sense_id(10))

    def test_accepts_oewn_homograph_pos_suffix(self):
        with tempfile.TemporaryDirectory() as temp_name:
            entries = Path(temp_name)
            (entries / "entries-b.yaml").write_text(
                "bow:\n"
                "  n-1:\n"
                "    sense:\n"
                "    - id: 'bow%1:06:03::'\n"
                "      synset: 02883431-n\n",
                encoding="utf-8",
            )
            records, _ = load_entries(entries)
        self.assertEqual(records[0]["senses"][0]["pos"], "noun")

    def test_reduces_oewn_frames_to_verb_grammar(self):
        self.assertEqual(
            grammar_from_subcats("verb", ["via", "vtai", "vii-adj"]),
            {"verb_type": ["transitive", "intransitive", "linking"]},
        )
        self.assertEqual(grammar_from_subcats("noun", ["vtai"]), {})

    def test_extracts_sense_specific_synonyms_and_antonyms(self):
        with tempfile.TemporaryDirectory() as temp_name:
            entries = Path(temp_name)
            (entries / "entries-h.yaml").write_text(
                "hot:\n  a:\n    sense:\n"
                "    - id: 'hot%3:00:00::'\n      synset: 001-a\n"
                "      antonym: ['cold%3:00:00::']\n"
                "warm:\n  a:\n    sense:\n"
                "    - id: 'warm%3:00:00::'\n      synset: 001-a\n"
                "cold:\n  a:\n    sense:\n"
                "    - id: 'cold%3:00:00::'\n      synset: 002-a\n",
                encoding="utf-8",
            )
            records, _ = load_entries(entries)
            assign_sense_ids(records, {})

        by_word = {record["word"]: record["senses"][0] for record in records}
        self.assertEqual(by_word["hot"]["synonyms"], ["warm"])
        self.assertEqual(by_word["warm"]["synonyms"], ["hot"])
        self.assertEqual(by_word["hot"]["antonyms"], ["cold"])
        self.assertNotIn("antonyms", by_word["cold"])

    def test_checked_in_core_has_valid_grammar(self):
        root = Path(__file__).parents[1]
        data_path = root / "packs/en/core/data.jsonl"
        metadata = json.loads(
            (root / "packs/en/core/meta.json").read_text(encoding="utf-8")
        )
        allowed = {"transitive", "intransitive", "linking"}
        grammar_count = 0
        synonym_count = 0
        antonym_count = 0
        for line in data_path.read_text(encoding="utf-8").splitlines():
            record = json.loads(line)
            self.assertNotIn("level", record)
            for sense in record["senses"]:
                grammar = sense.get("grammar", {})
                self.assertTrue(set(grammar) <= {"countability", "verb_type"})
                self.assertTrue(set(grammar.get("countability", ())) <= {"countable", "uncountable"})
                self.assertTrue(set(grammar.get("verb_type", ())) <= allowed)
                if "verb_type" in grammar:
                    self.assertEqual(sense["pos"], "verb")
                    grammar_count += 1
                for field in ("synonyms", "antonyms"):
                    values = sense.get(field, [])
                    self.assertEqual(len(values), len(set(values)))
                    self.assertTrue(all(isinstance(value, str) and value for value in values))
                    self.assertNotIn(record["word"].casefold(), {value.casefold() for value in values})
                synonym_count += "synonyms" in sense
                antonym_count += "antonyms" in sense
        self.assertEqual(metadata["schema_version"], 5)
        self.assertNotIn("with_level", metadata)
        self.assertNotIn("cefrj", metadata["sources"])
        self.assertEqual(metadata["senses_with_grammar"], grammar_count)
        self.assertEqual(metadata["senses_with_synonyms"], synonym_count)
        self.assertEqual(metadata["senses_with_antonyms"], antonym_count)
        self.assertEqual(metadata["output"]["sha256"], file_sha256(data_path))


if __name__ == "__main__":
    unittest.main()
