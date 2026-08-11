# Function-word Core Merge Design

## Goal

Make the 143 curated function-word records part of `packs/en/core/data.jsonl`
so every core search reads one table, while preserving exact sense IDs and
making these common forms rank ahead of ordinary lexical entries.

## Merge model

`packs/en/core/function-words.jsonl` remains the maintained source table;
`packs/en/core/sense-ids.tsv` remains the authoritative source-key-to-ID map.
A deterministic merge builder reads both plus core data.

For every supplemental row, it finds a core record by `word.casefold()`:

- if found, it appends `{id, pos}` to that record's `senses` only when the
  ID is not already present;
- if missing, it creates `{word, frequency, senses}` at the word's
  alphabetical location; and
- it rejects a source key missing from the registry, a reused ID, a malformed
  supplemental row, or an ID that conflicts with a different core sense.

No existing OEWN word, sense, ID, grammar, IPA, level, tag, or frequency is
removed. The same word may have both lexical and grammatical senses.

## Search order and priority

`core/data.jsonl` stays sorted by `(word.casefold(), word)`, not by priority.
This preserves predictable full-table and binary search for every word,
including `I` and words near the end of the alphabet.

The function-word table's lower numeric `priority` becomes a high search rank:
new core records receive that value as `frequency`; existing records use the
minimum of their present `frequency` and every linked supplemental priority.
Thus consumers can sort search suggestions by `frequency` ascending without
damaging the physical alphabetical index.

## Schema

The core sense POS enum is extended from OEWN's four lexical POS values to
also allow `pronoun`, `article`, `determiner`, `preposition`, `conjunction`,
`auxiliary`, `modal`, `negator`, `particle`, `discourse_adverb`, `quantifier`,
`distributive`, and `contraction`. Existing records remain schema-valid.

## Rebuild and verification

A single merge command writes a full, sorted JSONL payload atomically. Tests
prove duplicate-word sense append, new-word insertion, append-only IDs,
priority/frequency behavior, idempotency, schema-valid POS, and unchanged
non-supplement data. Final checks require all 143 supplement IDs exactly once
in core data and a successful full test suite.
