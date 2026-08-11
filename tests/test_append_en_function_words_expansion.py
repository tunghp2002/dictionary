import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.append_en_function_words_expansion import append_expansion
from scripts.build_en_function_words import build_function_word_queue, load_function_words


ROOT = Path(__file__).parents[1]
EXPANSION = ROOT / "packs/en/core/function-words-expansion.jsonl"


def existing(source_key: str) -> dict:
    return {"source_key": source_key, "word": "a", "pos": "article", "category": "article", "priority": 1, "description_hint": "Introduce an indefinite article.", "usage_hint": "Place it before a singular noun."}

EXPECTED = {
    "pronoun": "yourselves|somebody|anybody|everybody|nobody|something|anything|everything|nothing|one|ones|no-one|there|which|whose|one another|whoever|whomever|whatever|whichever".split("|"),
    "determiner": "her|what|such|same|less|least|several|various".split("|"),
    "quantifier": "plenty|half|a few|a little|a lot of|lots of|plenty of".split("|"),
    "auxiliary": "am|is|are|was|were|being|been|has|had|having|does|did|doing".split("|"),
    "modal": "shall|ought|need|dare|used to|have to|be going to|had better|be able to|gonna|wanna|gotta".split("|"),
    "preposition": "as|than|up|across|against|along|among|around|behind|below|beneath|beside|beyond|despite|down|during|except|inside|near|off|onto|opposite|outside|past|toward|underneath|until|upon|via|within|without|like|per|plus|throughout|towards|unlike|versus|out of".split("|"),
    "conjunction": "as|than|before|after|since|though|unless|until|whereas|whether|nor|once|provided|assuming|even if|as if|as though|so that|in case|for".split("|"),
    "discourse_adverb": "so|yet".split("|"),
    "adv": "where|when|why|how|wherever|whenever|however|somewhere|anywhere|everywhere|nowhere|else|kinda|sorta".split("|"),
    "particle": "away|back|down|in|off|on|over|around|along|apart|aside|by|forward|together".split("|"),
    "negator": "never|neither|nor".split("|"),
    "contraction": "I'd|you'd|we'd|they'd|he'd|she'd|it'd|mustn't|shan't|needn't|ain't|let's|that's|there's|here's|what's|who's|where's|when's|why's|how's|that'll|there'll|who'll|what'll|could've|should've|would've|might've|must've|lemme|dunno".split("|"),
}


class AppendEnFunctionWordsExpansionTest(unittest.TestCase):
    def test_expansion_has_the_exact_184_approved_pairs(self):
        rows = load_function_words(EXPANSION)
        self.assertEqual(184, len(rows))
        self.assertEqual(
            {(word, category) for category, words in EXPECTED.items() for word in words},
            {(row["word"], row["category"]) for row in rows},
        )
        informal = {row["word"] for row in rows if row.get("register") == "informal"}
        self.assertEqual({"ain't", "gonna", "wanna", "gotta", "kinda", "sorta", "lemme", "dunno"}, informal)

    def test_append_is_deterministic_and_idempotent(self):
        with tempfile.TemporaryDirectory() as name:
            target = Path(name) / "function-words.jsonl"
            target.write_text(json.dumps(existing("supplement:function:a:article")) + "\n", encoding="utf-8")
            self.assertEqual(184, append_expansion(target, EXPANSION))
            first = target.read_bytes()
            self.assertEqual(0, append_expansion(target, EXPANSION))
            self.assertEqual(first, target.read_bytes())

    def test_append_rejects_an_existing_expansion_pair(self):
        with tempfile.TemporaryDirectory() as name:
            target = Path(name) / "function-words.jsonl"
            target.write_text(json.dumps(existing("supplement:function:am:auxiliary")) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate source_key"):
                append_expansion(target, EXPANSION)

    def test_append_rejects_a_same_size_unapproved_inventory(self):
        with tempfile.TemporaryDirectory() as name:
            altered = Path(name) / "expansion.jsonl"
            altered.write_text(EXPANSION.read_text(encoding="utf-8").replace('"word":"yourselves"', '"word":"yourselvesx"', 1), encoding="utf-8")
            target = Path(name) / "function-words.jsonl"
            target.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "approved inventory"):
                append_expansion(target, altered)

    def test_no_one_uses_only_the_approved_hyphenated_key_exception(self):
        rows = load_function_words(EXPANSION)
        no_one = next(row for row in rows if (row["word"], row["category"]) == ("no-one", "pronoun"))
        self.assertEqual("supplement:function:no-one:pronoun:hyphenated", no_one["source_key"])

    def test_exactly_the_eight_informal_rows_are_priority_six_and_tagged(self):
        rows = load_function_words(EXPANSION)
        informal = {row["word"] for row in rows if row.get("register") == "informal"}
        self.assertEqual({"ain't", "gonna", "wanna", "gotta", "kinda", "sorta", "lemme", "dunno"}, informal)
        self.assertTrue(all(row["priority"] == 6 for row in rows if row["word"] in informal))
        self.assertTrue(all(row["priority"] != 6 and "register" not in row for row in rows if row["word"] not in informal))

    def test_rejects_a_nonexception_source_key(self):
        with tempfile.TemporaryDirectory() as name:
            altered = Path(name) / "expansion.jsonl"
            altered.write_text(EXPANSION.read_text(encoding="utf-8").replace('"source_key":"supplement:function:am:auxiliary"', '"source_key":"supplement:function:wrong:auxiliary"', 1), encoding="utf-8")
            (Path(name) / "source.jsonl").write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source_key"):
                append_expansion(Path(name) / "source.jsonl", altered)

    def test_rejects_reused_generic_hints(self):
        with tempfile.TemporaryDirectory() as name:
            altered = Path(name) / "expansion.jsonl"
            rows = [json.loads(line) for line in EXPANSION.read_text(encoding="utf-8").splitlines()]
            rows[1]["description_hint"] = rows[0]["description_hint"]
            rows[1]["usage_hint"] = rows[0]["usage_hint"]
            altered.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            (Path(name) / "source.jsonl").write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "reused hint"):
                append_expansion(Path(name) / "source.jsonl", altered)

    def test_preserves_every_historical_mapping_and_appends_contiguous_ids(self):
        historical = subprocess.run(["git", "show", "9add374:packs/en/core/function-words.jsonl"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        registry = subprocess.run(["git", "show", "9add374:packs/en/core/sense-ids.tsv"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        with tempfile.TemporaryDirectory() as name:
            root = Path(name); table = root / "table.jsonl"; ids = root / "ids.tsv"
            table.write_text(historical, encoding="utf-8"); ids.write_text(registry, encoding="utf-8")
            old = ids.read_bytes()
            self.assertEqual(184, append_expansion(table, EXPANSION))
            _, assigned = build_function_word_queue(table, ids)
            old_map = {line.split("\t", 1)[1] for line in old.decode().splitlines()[1:]}
            self.assertEqual({line.split("\t", 1)[1] for line in old.decode().splitlines()[1:]}, {key for key in assigned if key in old_map})
            new_ids = sorted(value for key, value in assigned.items() if key not in old_map)
            self.assertEqual(184, len(new_ids))
            self.assertEqual(list(range(new_ids[0], new_ids[-1] + 1)), new_ids)
