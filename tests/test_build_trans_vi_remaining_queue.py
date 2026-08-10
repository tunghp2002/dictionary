import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts.build_trans_vi_remaining_queue import build_remaining_queue


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


class BuildTransViRemainingQueueTest(unittest.TestCase):
    def test_writes_only_empty_canonical_senses_with_oewn_context(self):
        with tempfile.TemporaryDirectory() as temp_name:
            root = Path(temp_name)
            registry = root / "sense-ids.tsv"
            data = root / "data.jsonl"
            yaml_dir = root / "yaml"
            output = root / "queue.jsonl"
            yaml_dir.mkdir()
            registry.write_text(
                "sense_id\tsource_key\n1000000000007\talpha%1\n1000000000008\tbeta%1\n",
                encoding="utf-8",
            )
            write_jsonl(
                data,
                [
                    {"sense_id": 1000000000007, "meaning": "đầu tiên"},
                    {"sense_id": 1000000000008, "meaning": ""},
                ],
            )
            (yaml_dir / "entries-a.yaml").write_text(
                yaml.safe_dump(
                    {
                        "alpha": {"n": {"sense": [{"id": "alpha%1", "synset": "00000001-n"}]}},
                        "beta": {"n": {"sense": [{"id": "beta%1", "synset": "00000002-n"}]}},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )
            (yaml_dir / "noun.yaml").write_text(
                yaml.safe_dump(
                    {
                        "00000001-n": {"definition": ["first gloss"]},
                        "00000002-n": {"definition": ["second gloss"]},
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            count = build_remaining_queue(registry, data, yaml_dir, output)

            self.assertEqual(count, 1)
            self.assertEqual(
                read_jsonl(output),
                [{"sense_id": 1000000000008, "word": "beta", "pos": "noun", "gloss": ["second gloss"]}],
            )


if __name__ == "__main__":
    unittest.main()
