import json
import tempfile
import unittest
from pathlib import Path

from scripts.append_en_function_words_expansion import append_expansion
from scripts.build_en_function_words import load_function_words


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
