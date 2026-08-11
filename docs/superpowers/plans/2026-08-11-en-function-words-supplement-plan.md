# English Function-word Supplement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Add rich, priority-generated Vietnamese translations for common English function words that OEWN does not provide.

**Architecture:** A checked-in curated table is the source of truth for closed-class forms and contractions. A supplement builder appends stable registry IDs and makes a rich Luna Batch queue before OEWN retries. A canonical rebuild retains rich fields only on validated supplement records.

**Tech Stack:** Python 3.12 standard library, JSONL, OpenAI Responses Batch API with gpt-5.6-luna, unittest.

## Global Constraints

- Existing 185,129 sense IDs are immutable; new IDs append after the current maximum.
- Include only approved closed-class categories and contractions; no frequency-scraped open-class words.
- Canonical rows remain exactly sense_id, meaning, description, examples, and collocations.
- Function-word generation precedes residual OEWN retries; normal OEWN rows retain empty rich fields.
- Batch requests contain at most 25 forms and use low reasoning effort.
- Staged artifacts are ignored and API keys are never logged.

---

### Task 1: Curated source table and stable IDs

**Files:**
- Create: packs/en/core/function-words.jsonl
- Create: scripts/build_en_function_words.py
- Create: tests/test_build_en_function_words.py
- Modify: packs/en/core/sense-ids.tsv

**Interfaces:**
- Consumes JSONL records with source_key, word, pos, category, priority, description_hint, and usage_hint.
- Produces build_function_word_queue(table_path, registry_path) -> tuple[list[dict], dict[str, int]].

- [ ] **Step 1: Write failing tests**

    def test_queue_appends_ids_and_sorts_priority(tmp_path):
        rows, registry = build_function_word_queue(table_path, registry_path)
        assert [row["word"] for row in rows] == ["I", "you"]
        assert registry["supplement:function:i:pronoun"] == 1000000000002

    def test_rejects_open_class_or_duplicate_source_key(tmp_path):
        with self.assertRaisesRegex(ValueError, "duplicate source_key"):
            build_function_word_queue(duplicate_table, registry_path)

- [ ] **Step 2: Verify red**

    python -m unittest tests.test_build_en_function_words -v

Expected: module import fails.

- [ ] **Step 3: Implement minimal builder**

    def build_function_word_queue(table_path, registry_path):
        rows = load_function_words(table_path)
        registry = load_id_registry(registry_path)
        next_id = max(registry.values()) + 1
        for row in rows:
            registry.setdefault(row["source_key"], next_id)
            next_id = max(next_id, registry[row["source_key"]] + 1)
            row["sense_id"] = registry[row["source_key"]]
        return sorted(rows, key=lambda r: (r["priority"], r["word"].casefold(), r["source_key"])), registry

Validate category, contraction spelling, unique key, and required fields. Populate the full approved table: pronouns, determiners, quantifiers, prepositions, conjunctions, auxiliaries, modals, negators, particles, discourse adverbs, and contractions.

- [ ] **Step 4: Verify green**

    python -m unittest tests.test_build_en_function_words tests.test_build_core_en -v

- [ ] **Step 5: Commit**

    git add packs/en/core/function-words.jsonl packs/en/core/sense-ids.tsv scripts/build_en_function_words.py tests/test_build_en_function_words.py
    git commit -m "feat(en): add function word supplement"

### Task 2: Strict rich Luna pipeline

**Files:**
- Create: scripts/batch_trans_vi_luna_function_words.py
- Create: tests/test_batch_trans_vi_luna_function_words.py
- Modify: .gitignore

**Interfaces:**
- Consumes Task 1 queue rows.
- Produces ignored rich output, accepted rows, and retry queue under packs/en/trans-vi/review/function-words.

- [ ] **Step 1: Write failing schema and validation tests**

    def test_groups_at_most_25_and_requests_all_rich_fields():
        requests = build_requests(sample_rows(26), "gpt-5.6-luna", 25)
        assert len(requests) == 2
        assert set(schema_required_fields(requests[0])) == {
            "sense_id", "meaning", "description", "examples", "collocations"
        }

    def test_rich_row_requires_one_bilingual_example():
        assert validate_rich_row(valid_row()) is None
        assert validate_rich_row({**valid_row(), "examples": []}) == "expected one bilingual example"

- [ ] **Step 2: Verify red**

    python -m unittest tests.test_batch_trans_vi_luna_function_words -v

Expected: module import fails.

- [ ] **Step 3: Implement minimal pipeline**

Implement build_requests, validate_rich_row, prepare, submit, status, download, parse, and retry-queue. Require a concise Vietnamese headword, capitalized English description, exactly one non-empty en/vi example, and one to three natural collocations. Preserve valid siblings and retry only invalid IDs.

- [ ] **Step 4: Verify green**

    python -m unittest tests.test_batch_trans_vi_luna_function_words -v

- [ ] **Step 5: Commit**

    git add .gitignore scripts/batch_trans_vi_luna_function_words.py tests/test_batch_trans_vi_luna_function_words.py
    git commit -m "feat(trans-vi): add rich function word batches"

### Task 3: Rich-preserving canonical merge

**Files:**
- Create: scripts/merge_trans_vi_function_words.py
- Create: scripts/build_trans_vi_canonical.py
- Create: tests/test_merge_trans_vi_function_words.py
- Create: tests/test_build_trans_vi_canonical.py
- Modify: packs/en/trans-vi/data.jsonl, packs/en/trans-vi/seed.jsonl, packs/en/trans-vi/meta.json

**Interfaces:**
- Consumes registry, complete rich function-word rows, and all-sense meaning source.
- Produces canonical records for every registry ID.

- [ ] **Step 1: Write failing merge/rebuild tests**

    def test_merge_rejects_unknown_or_incomplete_id(tmp_path):
        with self.assertRaisesRegex(ValueError, "unknown supplement sense_id"):
            merge_function_words(data_path, rows_with_unknown_id)

    def test_rebuild_keeps_rich_fields_only_for_supplement(tmp_path):
        build_canonical(registry, source, data, seed, meta, supplement_ids={1000000000002})
        assert read(data)[1000000000002]["examples"]
        assert read(data)[1000000000001]["examples"] == []

- [ ] **Step 2: Verify red**

    python -m unittest tests.test_merge_trans_vi_function_words tests.test_build_trans_vi_canonical -v

Expected: module imports fail.

- [ ] **Step 3: Implement exact-coverage merge and rebuild**

Reject unknown, duplicate, malformed, or incomplete rich rows. Require every supplement ID exactly once. Rebuild every registry ID, retaining rich fields only when source_key starts supplement:function:. Recalculate data, seed, and meta from one validated payload.

- [ ] **Step 4: Verify green**

    python -m unittest tests.test_merge_trans_vi_function_words tests.test_build_trans_vi_canonical -v

- [ ] **Step 5: Commit**

    git add scripts/merge_trans_vi_function_words.py scripts/build_trans_vi_canonical.py tests/test_merge_trans_vi_function_words.py tests/test_build_trans_vi_canonical.py
    git commit -m "feat(trans-vi): preserve function word rich fields"

### Task 4: Generate, audit, and integrate

**Files:**
- Generate (ignored): packs/en/trans-vi/review/function-words/*
- Modify: canonical translation artifacts and notes-review.jsonl

**Interfaces:**
- Consumes Task 2 accepted output after its retry queue is empty.
- Produces one rich record for every supplement form and final canonical artifacts.

- [ ] **Step 1: Build and submit the priority queue**

    python scripts/build_en_function_words.py --table packs/en/core/function-words.jsonl --registry packs/en/core/sense-ids.tsv --queue packs/en/trans-vi/review/function-words/queue.jsonl
    python scripts/batch_trans_vi_luna_function_words.py prepare --queue packs/en/trans-vi/review/function-words/queue.jsonl --output packs/en/trans-vi/review/function-words/input.jsonl --group-size 25 --model gpt-5.6-luna
    python scripts/batch_trans_vi_luna_function_words.py submit --input packs/en/trans-vi/review/function-words/input.jsonl --metadata packs/en/trans-vi/review/function-words/batch.json --env C:\\Users\\T\\Downloads\\Test\\dictionary\\.env

- [ ] **Step 2: Parse and retry only failures**

Download terminal output, parse it, and submit only the retry queue until it is empty. Never re-submit accepted IDs.

- [ ] **Step 3: Audit every rich row**

Inspect every description, bilingual example, and collocation set for natural grammar-specific usage and no template duplication.

- [ ] **Step 4: Merge and rebuild**

    python scripts/merge_trans_vi_function_words.py --data packs/en/trans-vi/data.jsonl --registry packs/en/core/sense-ids.tsv --batch packs/en/trans-vi/review/function-words/accepted.jsonl
    python scripts/build_trans_vi_canonical.py --registry packs/en/core/sense-ids.tsv --source packs/en/trans-vi/data.jsonl --data packs/en/trans-vi/data.jsonl --seed packs/en/trans-vi/seed.jsonl --meta packs/en/trans-vi/meta.json

- [ ] **Step 5: Verify and integrate**

    python -m unittest discover -s tests -p "test_*.py" -v
    git diff --check

Assert the original 185,129 IDs are unchanged; each supplement ID is a complete rich record; all non-supplement rows have empty rich fields; and the meta checksum matches data. Commit and push only after the parallel OEWN retry results have merged.

