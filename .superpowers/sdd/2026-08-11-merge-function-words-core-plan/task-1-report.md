# Task 1 implementation report

## Changed files

- `scripts/merge_en_function_words_core.py`: added the atomic, idempotent core merge utility.
- `tests/test_merge_en_function_words_core.py`: added the required regression coverage for existing words, alphabetical insertion/idempotence, and registry/conflicting-ID rejection.
- `packs/en/core/data.jsonl`: merged all 143 curated function-word supplemental senses, preserving existing records and ordering records by case-folded word then spelling.
- `packs/en/core/schema.json`: added the 13 requested function-word POS values to the sense POS enum.
- `packs/en/core/meta.json`: updated only `output.sha256` and `output.bytes` to match the rewritten core JSONL. This is necessary because `tests.test_build_core_en` asserts the metadata SHA-256 equals the checked-in data file's SHA-256; no record metadata changed.

`packs/en/core/function-words.jsonl` and `packs/en/core/sense-ids.tsv` were verified unchanged.

## Validation

```powershell
python -m unittest tests.test_merge_en_function_words_core tests.test_build_core_en -v
```

Result: 9 tests passed.

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

Result: 82 tests passed.

```powershell
git diff --check
```

Result: exit 0 with no whitespace errors.

An additional real-data idempotence check reported `rows=143 idempotent=True`, and verified all 143 supplemental IDs occur exactly once in the merged core index.

## Self-review

- Source JSONL validation is delegated to the established `load_function_words` validator.
- Supplemental IDs are exclusively looked up through `load_id_registry`; the registry is never written or renumbered.
- Existing case-fold collisions in core data (for example `A`/`a`) select the exact source spelling when present, otherwise the case-fold match, so a supplemental ID remains unique.
- Writes use a same-directory temporary file plus `os.replace` for atomic replacement.

## Commit

`223b227` — `Merge function words into English core`

## Concerns

None. The only derived metadata update is the core output checksum and byte count required by the existing integrity test.

## Fix round 1: schema-valid supplemental POS

Review identified that the merge emitted the broad source `pos` labels. Six source rows use `adverb`, which is not a core schema enum value; other source rows similarly use broad labels such as `verb` where the curated category is more specific. The source `category` is the schema-supported function-word POS.

The merge now emits (and, on a repeat merge, normalizes) `row["category"]` for every supplemental sense. The checked-in core data was rebuilt, and the two derived core output fields in `meta.json` were refreshed.

Added `test_real_supplemental_senses_use_schema_pos_categories`, which resolves every real function-word source key through the ID registry and asserts its emitted core sense POS equals the source category and belongs to the core schema enum. The test first failed on the prior data with `verb != auxiliary`, then passed after the fix.

Validation run:

```powershell
python -m unittest tests.test_merge_en_function_words_core tests.test_build_core_en -v
python -m unittest discover -s tests -p "test_*.py" -v
git diff --check
```

Output: focused suite 10 tests passed; full suite 83 tests passed; `git diff --check` exited 0.

## Final review fixes: metadata summaries and supplemental-ID counts

Updated only the four stale derived values in `packs/en/core/meta.json` to
match the checked-in merged artifacts: `records=128092`, `senses=185272`,
`reserved_sense_ids=185272`, and `with_frequency=103895`. Core records, OEWN
IDs, and data contents are unchanged.

Added `test_checked_in_metadata_summary_matches_artifacts`, which derives the
record, sense, and frequency totals from `data.jsonl` and the reserved-ID
total from `sense-ids.tsv`, then compares each to `meta.json`.

Updated `test_real_supplemental_senses_use_schema_pos_categories` to count
occurrences with `Counter`, assert all 143 registry-derived supplemental IDs
are present, and assert each occurs exactly once while retaining POS/category
validation.

The metadata regression test failed before the metadata update with
`128009 != 128092`, then passed after the update.

Validation run:

```powershell
python -m unittest tests.test_merge_en_function_words_core tests.test_build_core_en -v
python -m unittest discover -s tests -p "test_*.py" -v
git diff --check
```

Output: focused suite 11 tests passed; full suite 84 tests passed; `git diff
--check` exited 0.

Fix commit: `2e592d5` — `Use function categories for core POS`.
