# English Function-word Supplement Design

## Goal

Add the high-frequency English closed-class words that OEWN omits, place them
ahead of outstanding OEWN work, and provide each new record with a concise
Vietnamese meaning, English description, bilingual example, and natural
collocations.

## Scope

The supplement is a curated, versioned table rather than a frequency scrape.
It contains these categories and the ordinary written contractions for the
same forms:

- personal, possessive, reflexive, demonstrative, relative, interrogative,
  indefinite, and reciprocal pronouns;
- articles, determiners, quantifiers, and distributives;
- common prepositions, coordinating and subordinating conjunctions;
- primary auxiliaries, modal auxiliaries, negators, particles, and basic
  discourse adverbs; and
- contractions such as `I'm`, `you're`, `don't`, `can't`, `won't`, and
  `they've`.

Open-class nouns, verbs, adjectives, and adverbs stay OEWN-owned. They are
not added merely because they are frequent; the existing OEWN pipeline already
covers those senses.

## Data and ID model

`packs/en/core/function-words.jsonl` is the authoritative supplement table.
Each row has a stable `source_key` beginning `supplement:function:`, a spelling,
POS, category, numeric priority, English definition, and example/collocation
guidance. The table is sorted by `(priority, word.casefold(), source_key)`.

The core registry receives new, append-only IDs after the highest existing
OEWN ID. Existing IDs, their meanings, and their ordering are never renumbered.
Priority affects only staging and model submission order: the supplement is
completely generated and validated before any residual OEWN retry is submitted.
It does not add a non-schema `priority` property to canonical translation rows.

## Generation

A dedicated Luna Batch builder consumes supplement context rather than OEWN
glosses. It uses a strict JSON schema and produces exactly:

- `sense_id` and a natural Vietnamese meaning (normally one to five words);
- a capitalized, punctuated English `description` that explains the English
  grammatical use without circular wording;
- exactly one natural `examples` object with non-empty `en` and `vi` text; and
- one to three lower-noise natural `collocations` appropriate to the form.

The generator uses `gpt-5.6-luna`, low reasoning effort, groups of at most 25
forms per request, and only retries records that fail validation or review.
This small group size makes the richer response reliable while keeping prompt
overhead and output cost low.

## Validation and merge

The validator rejects duplicate or unknown IDs; blank/malformed descriptions,
examples, or collocations; CJK/mojibake; sentence fragments as meanings; and
canonical records outside the five-field schema. It verifies every supplement
ID appears once in both the registry and canonical data.

The canonical rebuild retains rich fields supplied by the function-word
records and keeps every OEWN rich field empty. It recalculates `data.jsonl`,
`seed.jsonl`, and `meta.json` atomically from the registry and source rows.
Final checks require the old 185,129 IDs unchanged plus one rich, valid record
for every supplement ID.

## Failure handling

Batch output is staged under the ignored review path. Invalid or reviewer
rejected records are written to a supplement retry queue; valid siblings are
preserved. No supplement data is merged until exact coverage and schema checks
pass.
