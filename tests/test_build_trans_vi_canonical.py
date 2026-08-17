import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_trans_vi_canonical import build_canonical


class BuildTransViCanonicalTest(unittest.TestCase):
    def test_rebuild_keeps_rich_fields_for_every_sense(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            registry, source = root / "sense-ids.tsv", root / "source.jsonl"
            data, seed, meta = root / "data.jsonl", root / "seed.jsonl", root / "meta.json"
            registry.write_text(
                "sense_id\tsource_key\n1000000000001\toewn:one\n1000000000002\tsupplement:function:the:article\n",
                encoding="utf-8",
            )
            source.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in (
                {"sense_id": 1000000000001, "meaning": "mo\u0323\u0302t", "description": "Old detail.", "examples": [{"en": "One.", "vi": "Mo\u0323\u0302t."}], "collocations": ["one day"]},
                {"sense_id": 1000000000002, "meaning": "cái đó", "description": "Article used before a specific noun.", "examples": [{"en": "The book is here.", "vi": "Cuốn sách ở đây."}], "collocations": ["the book"]},
            )), encoding="utf-8")

            metadata = build_canonical(registry, source, data, seed, meta)

            rows = [json.loads(line) for line in data.read_text(encoding="utf-8").splitlines()]
            self.assertEqual([set(row) for row in rows], [{"sense_id", "meaning", "description", "examples", "collocations"}] * 2)
            self.assertEqual(rows[0], {"sense_id": 1000000000001, "meaning": "một", "description": "Old detail.", "examples": [{"en": "One.", "vi": "Một."}], "collocations": ["one day"]})
            self.assertEqual(rows[1]["examples"], [{"en": "The book is here.", "vi": "Cuốn sách ở đây."}])
            self.assertEqual(seed.read_bytes(), data.read_bytes())
            self.assertEqual(metadata["records"], 2)
            self.assertEqual(metadata["filled_records"], 2)
            self.assertEqual(metadata["placeholder_records"], 0)
            self.assertEqual(metadata["core_senses"], 2)
            self.assertEqual(metadata["license"], "CC-BY-SA-4.0")
            self.assertEqual(metadata["attribution"], "DATA_LICENSES.md")
            self.assertEqual(metadata["fields"], ["sense_id", "meaning", "description", "examples", "collocations"])
            self.assertEqual(metadata["output"]["sha256"], hashlib.sha256(data.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
