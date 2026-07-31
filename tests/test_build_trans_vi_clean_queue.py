import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.build_trans_vi_clean_queue import build_clean_queue


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


class BuildTransViCleanQueueTest(unittest.TestCase):
    def test_writes_oewn_only_rows_and_ignores_legacy_meanings(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            core = root / "data.jsonl"
            yaml_dir = root / "yaml"
            output = root / "review" / "clean-queue.jsonl"
            yaml_dir.mkdir()
            write_jsonl(
                core,
                [
                    {
                        "word": "alpha",
                        "frequency": 1,
                        "current_meaning": "NGHIA-CU-KHONG-DUOC-DUNG",
                        "senses": [{"id": 1000000000007}],
                    }
                ],
            )
            (root / "sense-ids.tsv").write_text(
                "sense_id\tsource_key\n1000000000007\talpha%1\n", encoding="utf-8"
            )
            (yaml_dir / "entries-a.yaml").write_text(
                yaml.safe_dump({"alpha": {"n": {"sense": [{"id": "alpha%1", "synset": "00000001-n"}]}}}, sort_keys=False),
                encoding="utf-8",
            )
            (yaml_dir / "noun.yaml").write_text(
                yaml.safe_dump({"00000001-n": {"definition": ["first gloss"]}}, sort_keys=False),
                encoding="utf-8",
            )

            count = build_clean_queue(core, yaml_dir, output)
            payload = output.read_text(encoding="utf-8")
            queue = [json.loads(line) for line in payload.splitlines()]

        self.assertEqual(count, 1)
        self.assertEqual(
            queue,
            [{"sense_id": 1000000000007, "word": "alpha", "pos": "noun", "gloss": ["first gloss"]}],
        )
        self.assertNotIn("NGHIA-CU-KHONG-DUOC-DUNG", payload)


if __name__ == "__main__":
    unittest.main()
