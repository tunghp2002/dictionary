# English Function-word Expansion Design

## Goal

Add a single curated expansion of 184 high-frequency English grammar senses to the existing function-word source table, then generate one complete rich Vietnamese translation row for each new sense and merge it into the canonical core and `trans-vi` packs.

## Scope

The pack extends grammar coverage only. It adds missing inflected auxiliaries, pronouns, determiners, quantifiers, prepositions, conjunctions, question/relative adverbs, particles, negators, and contractions. It also includes eight universally understood informal spoken forms, visibly tagged `informal`.

It does not add ordinary content-word senses merely because they are frequent, does not modify existing sense IDs or translations, and does not remove the existing 143 function-word rows.

## Data model

`packs/en/core/function-words.jsonl` remains the authoritative curated source. The existing required fields remain unchanged. New rows may contain an optional `register` field with the only value `informal`.

The function-word loader accepts the existing seven-field rows and the eight-field form with `register`. It permits the existing categories plus `adv`. The merger emits the source category as the core POS; an informal row emits `tags: {"register": ["informal"]}` on its supplemental sense. It permits a contraction without an apostrophe only when that row is explicitly `register: "informal"`.

The core schema already permits `adv` and `tags.register: informal`; no existing core record changes except frequency priority and appended supplemental senses. IDs are append-only registry entries. New records stay sorted by `(word.casefold(), word)`; existing records use the lowest numeric priority of all linked function senses.

The historical `no one` mapping `supplement:function:no-one:pronoun` is immutable. The new hyphenated `no-one` pronoun is the sole source-key exception and uses `supplement:function:no-one:pronoun:hyphenated`; every other expansion row uses `supplement:function:<word.casefold()>:<category>`.

## Exact 184-sense inventory

Each semicolon-separated item below is one new row, except an item repeated in different category sections intentionally receives one sense per grammatical role.

| Category | Count | Items |
|---|---:|---|
| `pronoun` | 20 | yourselves; somebody; anybody; everybody; nobody; something; anything; everything; nothing; one; ones; no-one; there; which; whose; one another; whoever; whomever; whatever; whichever |
| `determiner` | 8 | her; what; such; same; less; least; several; various |
| `quantifier` | 7 | plenty; half; a few; a little; a lot of; lots of; plenty of |
| `auxiliary` | 13 | am; is; are; was; were; being; been; has; had; having; does; did; doing |
| `modal` | 12 | shall; ought; need; dare; used to; have to; be going to; had better; be able to; gonna *(informal)*; wanna *(informal)*; gotta *(informal)* |
| `preposition` | 39 | as; than; up; across; against; along; among; around; behind; below; beneath; beside; beyond; despite; down; during; except; inside; near; off; onto; opposite; outside; past; toward; underneath; until; upon; via; within; without; like; per; plus; throughout; towards; unlike; versus; out of |
| `conjunction` | 20 | as; than; before; after; since; though; unless; until; whereas; whether; nor; once; provided; assuming; even if; as if; as though; so that; in case; for |
| `discourse_adverb` | 2 | so; yet |
| `adv` | 14 | where; when; why; how; wherever; whenever; however; somewhere; anywhere; everywhere; nowhere; else; kinda *(informal)*; sorta *(informal)* |
| `particle` | 14 | away; back; down; in; off; on; over; around; along; apart; aside; by; forward; together |
| `negator` | 3 | never; neither; nor |
| `contraction` | 32 | I'd; you'd; we'd; they'd; he'd; she'd; it'd; mustn't; shan't; needn't; ain't *(informal)*; let's; that's; there's; here's; what's; who's; where's; when's; why's; how's; that'll; there'll; who'll; what'll; could've; should've; would've; might've; must've; lemme *(informal)*; dunno *(informal)* |

## Rich translations

Each new ID receives exactly the canonical translation fields:

```json
{"sense_id": 1000000000000, "meaning": "...", "description": "...", "examples": [{"en": "...", "vi": "..."}], "collocations": ["..."]}
```

`meaning` is concise natural Vietnamese. `description` is a specific English explanation of that particular grammatical role. There is exactly one natural bilingual example and one to three useful collocations; a generic POS template is invalid. Informal forms explicitly say they are informal in the description and carry the core `informal` tag.

## Priority

Priority 1 covers personal/auxiliary/modal essentials and the most common contractions. Priorities 2–5 cover ordinary grammar variants by frequency; priority 6 is reserved for informal forms and less universal variants. A lower numeric value remains higher priority.

## Validation and merge

Tests must prove:

- The exact 184 inventory is present once by `(word, category)` and every informal item has the informal register.
- Existing seven-field rows remain accepted; invalid register/category combinations and untagged apostrophe-free contractions are rejected.
- The registry preserves all old IDs and allocates exactly 184 new append-only IDs deterministically.
- Core merge preserves all existing records, creates the correct new sense tags, validates against the core schema, keeps every supplemental ID exactly once, and is idempotent.
- Rich batch parsing covers all 184 new IDs and rejects missing, generic, malformed, or wrong-register rows.
- Canonical core and `trans-vi` metadata/checksums match their data after merge.

No API request may be sent until the inventory queue and its test validation are clean. The Luna batch prompt sends only the public curated fields needed to generate the rich translation rows.
