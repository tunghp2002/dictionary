# Top 30,000 English Lemmas: Vietnamese Translation Design

## Goal

Fill the English-to-Vietnamese pack for the 30,000 most frequent English lemmas in `packs/en/core/data.jsonl`, while adding a concise English `description` for every covered sense.

## Scope

The target is the first 30,000 core records sorted by `(frequency, word.casefold())`. Every sense belonging to those lemmas is included. The audit found 57,446 target senses; 57,438 already have a Vietnamese meaning and 8 are blank. Existing meanings are eligible for shortening when they exceed the concise target style.

Every translation record will contain the new `description` string; target records
must have a non-empty value and non-target placeholders use `""`.

Each target translation record will contain:

```json
{
  "sense_id": 1000000000001,
  "meaning": "nghĩa ngắn",
  "description": "A short English dictionary description.",
  "examples": [],
  "collocations": []
}
```

`description` comes from the pinned Open English WordNet 2025 gloss for the sense. It is source text, not an invented encyclopedia entry. The source attribution remains covered by the existing project license documentation.

## Quality rules

- `meaning` is natural Vietnamese, normally 1–5 words and at most 35 characters.
- `description` is non-empty English text tied to the exact sense.
- Sense distinctions are preserved; no merging across parts of speech or polysemous senses.
- Existing examples and collocations are preserved.
- A staging file is generated and validated before the checked-in seed/data files are changed.
- Validators reject missing/duplicate target IDs, non-target IDs, CJK text in meanings, empty descriptions, and schema-field drift.

## Workflow

1. Fetch the pinned OEWN snapshot using the existing source-fetch workflow.
2. Derive the deterministic target lemma and sense ID set from core frequency data.
3. Generate review batches containing sense ID, word, POS, source gloss, current meaning, and proposed description/meaning.
4. Use the selected low-cost agent model for structured proposals in bounded batches; run a separate review pass over each batch.
5. Run deterministic validation and human spot checks for ambiguous, idiomatic, offensive, and highly polysemous senses.
6. Merge approved records into `seed.jsonl`, rebuild `data.jsonl` and `meta.json`, and run the full test suite.

## Compatibility

The translation schema, skeleton builder, DeepSeek helper's record-shaping logic, review-note builder, metadata field list, and translation tests must all accept and preserve `description`. Non-target senses remain placeholders with an empty `description`; the final target output requires a non-empty description.

## Failure handling

Failed batches remain in staging with their error report and are not merged. Re-running a batch is idempotent by `sense_id`; the merge step rejects conflicting duplicate IDs. The original pack is retained until validation passes.

## Verification

The implementation is complete only when the target set contains exactly 57,446 records, all target descriptions are non-empty, all target meanings satisfy the concise rules, JSONL/schema validation passes, metadata checksums match, and `python -m unittest discover -s tests` passes.
