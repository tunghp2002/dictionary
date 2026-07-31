import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.build_trans_vi_target import build_target_manifest, select_target_words


def write_jsonl(path, rows):
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )


class BuildTransViTargetTest(unittest.TestCase):
    def test_selector_orders_frequency_ties_by_casefolded_word(self):
        with tempfile.TemporaryDirectory() as temp_name:
            core = Path(temp_name) / "core.jsonl"
            write_jsonl(
                core,
                [
                    {"word": "zebra", "frequency": 1, "senses": []},
                    {"word": "Apple", "frequency": 1, "senses": []},
                    {"word": "banana", "frequency": 0, "senses": []},
                ],
            )
            self.assertEqual(
                [row["word"] for row in select_target_words(core, limit=3)],
                ["banana", "Apple", "zebra"],
            )

    def test_selector_places_words_without_frequency_after_ranked_words(self):
        with tempfile.TemporaryDirectory() as temp_name:
            core = Path(temp_name) / "core.jsonl"
            write_jsonl(
                core,
                [
                    {"word": "unranked", "senses": []},
                    {"word": "ranked", "frequency": 1, "senses": []},
                ],
            )
            self.assertEqual(
                [row["word"] for row in select_target_words(core, limit=2)],
                ["ranked", "unranked"],
            )

    def test_selector_returns_exactly_30000_lemmas(self):
        with tempfile.TemporaryDirectory() as temp_name:
            core = Path(temp_name) / "core.jsonl"
            write_jsonl(
                core,
                [
                    {"word": f"word-{index:05d}", "frequency": index, "senses": []}
                    for index in range(30001)
                ],
            )
            selected = select_target_words(core)
        self.assertEqual(len(selected), 30000)
        self.assertEqual(selected[-1]["word"], "word-29999")

    def test_manifest_deduplicates_target_ids_and_writes_context_queue(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            core = root / "core.jsonl"
            translations = root / "translations.jsonl"
            yaml_dir = root / "yaml"
            yaml_dir.mkdir()
            manifest_path = root / "target-manifest.json"
            write_jsonl(
                core,
                [
                    {"word": "alpha", "frequency": 1, "senses": [{"id": 1000000000007, "pos": "noun"}]},
                    {"word": "beta", "frequency": 2, "senses": [{"id": 1000000000007, "pos": "noun"}, {"id": 1000000000008, "pos": "verb"}]},
                ],
            )
            (root / "sense-ids.tsv").write_text(
                "sense_id\tsource_key\n1000000000007\talpha%1\n1000000000008\tbeta%2\n", encoding="utf-8"
            )
            write_jsonl(translations, [{"sense_id": 1000000000007, "meaning": " alpha ", "description": "d", "examples": [{"en": "e", "vi": "v"}], "collocations": ["c"]}])
            (yaml_dir / "entries-a.yaml").write_text(
                yaml.safe_dump({"alpha": {"n": {"sense": [{"id": "alpha%1", "synset": "00000001-n"}]}}, "beta": {"v": {"sense": [{"id": "beta%2", "synset": "00000002-v"}]} }}, sort_keys=False),
                encoding="utf-8",
            )
            (yaml_dir / "noun.yaml").write_text(
                yaml.safe_dump({"00000001-n": {"definition": ["first"], "example": ["an alpha"]}, "00000002-v": {"definition": ["second"]}}, sort_keys=False),
                encoding="utf-8",
            )

            manifest = build_target_manifest(core, translations, yaml_dir, manifest_path)
            queue = [json.loads(line) for line in (root / "review" / "queue.jsonl").read_text(encoding="utf-8").splitlines()]

        self.assertEqual(manifest["target_sense_ids"], [1000000000007, 1000000000008])
        self.assertEqual(manifest["target_senses"], 2)
        self.assertEqual([row["sense_id"] for row in queue], [1000000000007, 1000000000008])
        self.assertEqual(
            queue[0],
            {"sense_id": 1000000000007, "word": "alpha", "pos": "noun", "gloss": ["first"], "current_meaning": "alpha", "description": "d", "examples": [{"en": "e", "vi": "v"}], "collocations": ["c"]},
        )
        self.assertEqual(queue[1]["current_meaning"], "")


if __name__ == "__main__":
    unittest.main()
