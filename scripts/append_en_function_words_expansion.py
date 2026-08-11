#!/usr/bin/env python3
"""Validate and append the curated English function-word expansion once."""

from __future__ import annotations

import os
from pathlib import Path

from scripts.build_en_function_words import load_function_words

INVENTORY = {
    "pronoun": "yourselves|somebody|anybody|everybody|nobody|something|anything|everything|nothing|one|ones|no-one|there|which|whose|one another|whoever|whomever|whatever|whichever",
    "determiner": "her|what|such|same|less|least|several|various", "quantifier": "plenty|half|a few|a little|a lot of|lots of|plenty of",
    "auxiliary": "am|is|are|was|were|being|been|has|had|having|does|did|doing", "modal": "shall|ought|need|dare|used to|have to|be going to|had better|be able to|gonna|wanna|gotta",
    "preposition": "as|than|up|across|against|along|among|around|behind|below|beneath|beside|beyond|despite|down|during|except|inside|near|off|onto|opposite|outside|past|toward|underneath|until|upon|via|within|without|like|per|plus|throughout|towards|unlike|versus|out of",
    "conjunction": "as|than|before|after|since|though|unless|until|whereas|whether|nor|once|provided|assuming|even if|as if|as though|so that|in case|for", "discourse_adverb": "so|yet",
    "adv": "where|when|why|how|wherever|whenever|however|somewhere|anywhere|everywhere|nowhere|else|kinda|sorta", "particle": "away|back|down|in|off|on|over|around|along|apart|aside|by|forward|together",
    "negator": "never|neither|nor", "contraction": "I'd|you'd|we'd|they'd|he'd|she'd|it'd|mustn't|shan't|needn't|ain't|let's|that's|there's|here's|what's|who's|where's|when's|why's|how's|that'll|there'll|who'll|what'll|could've|should've|would've|might've|must've|lemme|dunno",
}
APPROVED_PAIRS = {(word, category) for category, words in INVENTORY.items() for word in words.split("|")}
INFORMAL_WORDS = {"ain't", "gonna", "wanna", "gotta", "kinda", "sorta", "lemme", "dunno"}
NO_ONE_EXCEPTION = ("no-one", "pronoun")

def append_expansion(source_path: Path, expansion_path: Path) -> int:
    """Append the complete expansion atomically, or leave the source unchanged."""
    expansion = load_function_words(expansion_path)
    if len(expansion) != 184 or {(row["word"], row["category"]) for row in expansion} != APPROVED_PAIRS:
        raise ValueError("expansion must contain the approved inventory")
    hints = [(row["description_hint"], row["usage_hint"]) for row in expansion]
    if len(set(hints)) != len(hints):
        raise ValueError("reused hint in expansion")
    for row in expansion:
        pair = (row["word"], row["category"])
        expected_key = f"supplement:function:{row['word'].casefold()}:{row['category']}"
        if pair == NO_ONE_EXCEPTION:
            expected_key += ":hyphenated"
        if row["source_key"] != expected_key:
            raise ValueError(f"invalid source_key: {row['source_key']}")
        is_informal = row["word"] in INFORMAL_WORDS
        if is_informal != (row.get("register") == "informal") or is_informal != (row["priority"] == 6):
            raise ValueError(f"invalid informal metadata: {row['word']}")
        if not is_informal and ("register" in row or row["priority"] == 6):
            raise ValueError(f"invalid standard metadata: {row['word']}")
    expansion_keys = {row["source_key"] for row in expansion}
    if len(expansion_keys) != 184:
        raise ValueError("duplicate source_key in expansion")
    existing = load_function_words(source_path)
    existing_keys = {row["source_key"] for row in existing}
    overlap = existing_keys & expansion_keys
    if overlap == expansion_keys:
        return 0
    existing_pairs = {(row["word"], row["category"]) for row in existing}
    pair_overlap = existing_pairs & {(row["word"], row["category"]) for row in expansion}
    if pair_overlap:
        raise ValueError(f"duplicate pair: {sorted(pair_overlap)[0]}")
    if overlap:
        raise ValueError(f"duplicate source_key: {sorted(overlap)[0]}")
    payload = source_path.read_text(encoding="utf-8")
    if payload and not payload.endswith("\n"):
        payload += "\n"
    temporary = source_path.with_suffix(source_path.suffix + ".tmp")
    temporary.write_text(payload + expansion_path.read_text(encoding="utf-8"), encoding="utf-8")
    os.replace(temporary, source_path)
    return len(expansion)
