# Function-word Core Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task.

**Goal:** Merge curated function-word senses into one searchable core table.

**Architecture:** A deterministic Python merger joins function-words.jsonl, sense-ids.tsv, and core data by casefolded word. It appends new senses to matching records, inserts missing records at alphabetic positions, and uses lower numeric frequency as higher priority.

**Tech Stack:** Python standard library, JSONL, unittest.

## Global Constraints

- Preserve every existing core record, OEWN ID, and metadata exactly.
- Supplement IDs come only from the registry; never allocate or renumber IDs.
- Sort physical data by word.casefold()/word; priority uses frequency.
- Add grammar POS values to the core schema.
- Require each supplemental ID exactly once after merge and retain idempotency.

### Task 1: Merge and validate core data

**Files:**
- Create: scripts/merge_en_function_words_core.py
- Create: tests/test_merge_en_function_words_core.py
- Modify: packs/en/core/schema.json
- Modify: packs/en/core/data.jsonl

**Interfaces:** `merge_function_words_into_core(core_path, function_words_path, registry_path) -> int` mutates core_path atomically and returns the source-row count.

- [ ] **Step 1: Write failing tests**

    def test_existing_word_gets_new_sense_and_priority(tmp_path):
        merge_function_words_into_core(core, forms, registry)
        record = find_word(core, "I")
        assert {sense["id"] for sense in record["senses"]} == {1000000000001, 1000000000003}
        assert record["frequency"] == 1

    def test_missing_word_is_inserted_alphabetically_and_merge_is_idempotent(tmp_path):
        merge_function_words_into_core(core, forms, registry)
        first = read_jsonl(core)
        merge_function_words_into_core(core, forms, registry)
        assert read_jsonl(core) == first
        assert [row["word"] for row in first] == ["a", "I", "zoo"]

    def test_missing_registry_and_conflicting_id_are_rejected(tmp_path):
        with self.assertRaisesRegex(ValueError, "missing registry"):
            merge_function_words_into_core(core, forms, empty_registry)

- [ ] **Step 2: Run red**

    python -m unittest tests.test_merge_en_function_words_core -v

Expected: module import fails.

- [ ] **Step 3: Implement**

Read and validate JSONL source rows; map supplemental source keys through load_id_registry; append `{id, pos}` without duplicates; reject an ID already owned by a different word; assign min(existing frequency, priority); and atomically write sorted records. Extend core POS enum with pronoun, article, determiner, preposition, conjunction, auxiliary, modal, negator, particle, discourse_adverb, quantifier, distributive, and contraction.

- [ ] **Step 4: Verify green**

    python -m unittest tests.test_merge_en_function_words_core tests.test_build_core_en -v
    python -m unittest discover -s tests -p "test_*.py" -v
    git diff --check

- [ ] **Step 5: Commit and push**

    git add packs/en/core/data.jsonl packs/en/core/schema.json scripts/merge_en_function_words_core.py tests/test_merge_en_function_words_core.py
    git commit -m "feat(core): merge function word senses"
    git push origin dev
