# Top 30,000 Translation Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add English descriptions and concise Vietnamese meanings for the 57,446 senses belonging to the 30,000 highest-frequency English lemmas.

**Architecture:** Keep the canonical 185,129-sense skeleton intact, add a `description` field to every translation record, and generate a deterministic target manifest from core frequency. Use OEWN glosses as descriptions, staging JSONL for model proposals/review, and a merge validator that only promotes complete target records into the seed.

**Tech Stack:** Python 3.11 standard library, existing PyYAML source loader, JSONL, unittest, pinned OEWN 2025 snapshot.

## Global Constraints

- Target selection is the first 30,000 core records sorted by `(frequency, word.casefold())`.
- Target size is exactly 57,446 senses.
- Target `meaning` is Vietnamese, normally 1–5 words and at most 35 characters.
- Target `description` is non-empty English OEWN gloss text; non-target placeholders use `""`.
- Preserve existing `examples` and `collocations`.
- Never write directly to canonical `data.jsonl` from a batch worker; merge by `sense_id` after validation.

---

### Task 1: Extend translation schema and skeleton

**Files:**
- Modify: `packs/en/trans-vi/schema.json`
- Modify: `scripts/build_trans_vi_skeleton.py`
- Modify: `scripts/fill_trans_vi_deepseek.py`
- Modify: `packs/en/trans-vi/meta.json` through the rebuild command
- Test: `tests/test_build_trans_vi.py`

**Interfaces:**
- `translation_record(sense_id, meaning, record)` returns a record with `description` preserved/defaulting to `""`.
- Skeleton records always include `description: ""` when no seed exists.

- [ ] Add `description` as a required string property and include it in the schema field list.
- [ ] Update record shaping, seed merge, and skeleton defaults to preserve descriptions.
- [ ] Extend the existing translation tests to assert exact fields and placeholder description behavior.
- [ ] Run `python -m unittest tests.test_build_trans_vi -v` and rebuild the pack metadata.
- [ ] Commit the schema/script/test change.

### Task 2: Build deterministic target manifest and OEWN staging queue

**Files:**
- Create: `scripts/build_trans_vi_target.py`
- Create: `tests/test_build_trans_vi_target.py`
- Create: `packs/en/trans-vi/target-manifest.json`
- Create: `packs/en/trans-vi/review/queue.jsonl` (generated, gitignored if needed)

**Interfaces:**
- `select_target_words(core_path, limit=30000) -> list[dict]` sorts by `(frequency, word.casefold())`.
- `build_target_manifest(core_path, translation_path, oewn_yaml, output_path) -> dict` writes target IDs and source context.

- [ ] Write failing tests for tie ordering, exact 30,000 lemma selection, and target ID deduplication.
- [ ] Implement the selector and manifest writer using only standard-library JSONL parsing plus the existing OEWN context loader.
- [ ] Include `sense_id`, `word`, `pos`, `gloss`, `current_meaning`, `description`, `examples`, and `collocations` in each queue row.
- [ ] Fetch the pinned source snapshot with `python scripts/fetch_sources.py` if `.cache/sources/oewn-2025` is absent.
- [ ] Generate the manifest and assert it contains exactly 57,446 target senses.
- [ ] Commit the manifest builder and tests.

### Task 3: Add batch validator and safe merge

**Files:**
- Create: `scripts/validate_trans_vi_batches.py`
- Create: `scripts/merge_trans_vi_batches.py`
- Create: `tests/test_validate_trans_vi_batches.py`

**Interfaces:**
- `validate_batch(path, target_ids, require_descriptions=True) -> list[str]` returns deterministic error strings.
- `merge_batches(batch_paths, seed_path, target_ids, output_path) -> int` writes only validated, non-conflicting records and returns merged count.

- [ ] Test rejection of duplicate IDs, non-target IDs, empty target descriptions, overlong meanings, CJK text, and field drift.
- [ ] Implement validation without network access and with stable sorted output.
- [ ] Implement idempotent merge by `sense_id`; reject conflicting duplicates and preserve non-target seed records.
- [ ] Run focused validator tests and commit.

### Task 4: Generate and review target batches

**Files:**
- Create: `packs/en/trans-vi/review/batches/*.jsonl` (staging artifacts)
- Modify: `packs/en/trans-vi/seed.jsonl` only through the merge command

**Interfaces:**
- Each batch contains at most 250 target records and uses the queue row contract from Task 2.

- [ ] Partition the queue deterministically into batches of 250 by target rank.
- [ ] Have the selected low-cost agent model produce concise Vietnamese meanings and preserve OEWN descriptions, writing one shard per batch.
- [ ] Run a separate review pass over every shard; revise ambiguous, idiomatic, offensive, and polysemous senses.
- [ ] Run the validator on all shards and record failures without merging them.
- [ ] Merge only approved shards and verify all 57,446 target IDs are present exactly once.

### Task 5: Rebuild, verify, and document output

**Files:**
- Modify: `packs/en/trans-vi/data.jsonl` through `scripts/build_trans_vi_skeleton.py`
- Modify: `packs/en/trans-vi/meta.json`
- Modify: `README.md`

**Interfaces:**
- Final metadata lists `description` in `fields`, records exactly 185,129, and reports the matching SHA-256.

- [ ] Rebuild canonical data and metadata from the merged seed.
- [ ] Add README documentation for target selection, description provenance, and concise meaning rules.
- [ ] Run `python -m unittest discover -s tests`.
- [ ] Run a final JSONL audit for 57,446 non-empty target descriptions and valid target meanings.
- [ ] Commit the completed data/schema/documentation changes.
