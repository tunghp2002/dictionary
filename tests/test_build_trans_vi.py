import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_trans_vi import (
    has_cjk,
    load_pwn30_sense_synsets,
    load_vietnamese_lemmas,
    normalize_synset,
)
from scripts.build_core_en import file_sha256, load_id_registry


class BuildTransViTest(unittest.TestCase):
    def test_normalizes_satellite_synsets(self):
        self.assertEqual(normalize_synset(1188475, "s"), "01188475-a")

    def test_loads_vietnamese_lemmas_and_filters_non_vietnamese_script(self):
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "vie.tab"
            path.write_text(
                "# source\n"
                "00000001-n\tvie:lemma\tnặng\n"
                "00000001-n\tvie:lemma\tnặng\n"
                "00000001-n\tvie:lemma\t勇敢\n"
                "00000001-n\tvie:def\tignored\n",
                encoding="utf-8",
            )
            self.assertEqual(load_vietnamese_lemmas(path), {"00000001-n": ["nặng"]})

    def test_loads_princeton_sense_index(self):
        with tempfile.TemporaryDirectory() as temp_name:
            path = Path(temp_name) / "index.sense"
            path.write_text("run%2:38:00:: 01888511 2 0\n", encoding="utf-8")
            self.assertEqual(
                load_pwn30_sense_synsets(path), {"run%2:38:00::": "01888511-v"}
            )

    def test_curated_pack_is_sorted_and_references_core_ids(self):
        root = Path(__file__).parents[1]
        data_path = root / "packs/en/trans-vi/data.jsonl"
        metadata_path = root / "packs/en/trans-vi/meta.json"
        registry = set(load_id_registry(root / "packs/en/core/sense-ids.tsv").values())
        rows = [json.loads(line) for line in data_path.read_text(encoding="utf-8").splitlines()]
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        ids = [row["sense_id"] for row in rows]
        self.assertEqual(ids, sorted(ids))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(set(ids) <= registry)
        fields = {"sense_id", "meaning", "examples", "collocations"}
        self.assertTrue(all(set(row) == fields for row in rows))
        filled = [row for row in rows if row["meaning"]]
        self.assertTrue(all(not has_cjk(row["meaning"]) for row in filled))
        self.assertTrue(
            all(
                row["meaning"] == ""
                and row["examples"] == []
                and row["collocations"] == []
                for row in rows
                if not row["meaning"]
            )
        )
        self.assertTrue(
            all(
                isinstance(example, dict)
                and set(example) == {"en", "vi"}
                for row in rows
                for example in row["examples"]
            )
        )
        self.assertTrue(all(isinstance(item, str) for row in rows for item in row["collocations"]))
        self.assertEqual(metadata["records"], len(rows))
        self.assertEqual(metadata["filled_records"], len(filled))
        self.assertEqual(metadata["placeholder_records"], len(rows) - len(filled))
        self.assertEqual(metadata["core_senses"], len(registry))
        self.assertAlmostEqual(metadata["coverage"], len(filled) / len(registry))
        self.assertEqual(
            metadata["fields"], ["sense_id", "meaning", "examples", "collocations"]
        )
        self.assertEqual(metadata["output"]["sha256"], file_sha256(data_path))


if __name__ == "__main__":
    unittest.main()
