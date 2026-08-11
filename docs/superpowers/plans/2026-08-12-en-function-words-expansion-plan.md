# English Function-word Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the approved 184-sense high-frequency English grammar expansion to core and rich Vietnamese translations.

**Architecture:** A checked-in expansion manifest is validated and appended deterministically to the authoritative function-word table. Registry IDs are append-only; the core merger emits POS and optional informal tags. A single Luna Batch produces rich translations for only the 184 new IDs; validated output is combined with the existing 143 rich rows and canonical packs are rebuilt.

**Tech Stack:** Python standard library, JSONL, unittest, existing OpenAI Batch/Luna scripts.

## Global Constraints

- Use the exact 184 `(word, category)` pairs from `docs/superpowers/specs/2026-08-12-en-function-words-expansion-design.md`; no extra rows and no omitted rows.
- Preserve every existing function-word row, core record, sense ID, translation, and metadata field unless it is a derived count/checksum affected by the merge.
- New source IDs use `supplement:function:<word.casefold()>:<category>` and are append-only in `packs/en/core/sense-ids.tsv`.
- The only informal forms are `ain't`, `gonna`, `wanna`, `gotta`, `kinda`, `sorta`, `lemme`, and `dunno`; each carries `register: informal`.
- `adv` is the POS/category for question/relative adverbs; do not mislabel them `discourse_adverb`.
- New rich rows use exactly `sense_id`, `meaning`, `description`, `examples`, `collocations`; one bilingual example; one to three collocations; concise Vietnamese; and a role-specific English description.
- Do not send API traffic until local manifest/core tests are green. Batch input contains only public curated function-word fields and sense IDs.
- Batch queues, input, metadata, and output live only under ignored `packs/en/trans-vi/review/function-words-expansion/`.

---

### Task 1: Validate and append the exact expansion source

**Files:**
- Create: `packs/en/core/function-words-expansion.jsonl`
- Create: `scripts/append_en_function_words_expansion.py`
- Create: `tests/test_append_en_function_words_expansion.py`
- Modify: `scripts/build_en_function_words.py`
- Modify: `tests/test_build_en_function_words.py`
- Modify: `.gitignore`
- Modify: `packs/en/core/function-words.jsonl`
- Modify: `packs/en/core/sense-ids.tsv`

**Interfaces:**
- `load_function_words(path: Path) -> list[dict[str, Any]]` accepts the legacy seven-field row or an eight-field row adding `register`; its only value is `informal`.
- `append_expansion(source_path: Path, expansion_path: Path) -> int` validates all 184 approved pairs, rejects duplicate source key/pair, atomically appends rows in `(priority, word.casefold(), source_key)` order, and returns `184`.

- [ ] **Step 1: Write failing tests**

Add fixtures for a legacy row, an informal apostrophe-free contraction, and an untagged apostrophe-free contraction. Add:

```python
def test_loads_legacy_and_tagged_informal_rows(tmp_path):
    assert load_function_words(table) == [legacy_row, informal_row]

def test_rejects_untagged_apostrophe_free_contraction(tmp_path):
    with self.assertRaisesRegex(ValueError, "invalid contraction spelling"):
        load_function_words(table)

def test_expansion_has_exact_inventory_and_appends_once(tmp_path):
    assert append_expansion(source, expansion) == 184
    assert append_expansion(source, expansion) == 184
    assert pairs(source) == original_pairs | expansion_pairs
```

- [ ] **Step 2: Run red**

Run: `python -m unittest tests.test_build_en_function_words tests.test_append_en_function_words_expansion -v`

Expected: FAIL because optional register support, `adv`, the append utility, and the expansion manifest do not exist.

- [ ] **Step 3: Implement source data and loader support**

Create one JSONL row for every exact design-inventory item. Use the required source-key form, clear grammar-specific `description_hint` and `usage_hint`, priorities 1–5 for standard forms and 6 for informal forms. Give exactly the eight approved informal rows `"register":"informal"`.

Permit `adv`. Permit `register` only with `informal`. Keep the apostrophe rule for `contraction` unless a row is tagged informal. The append utility compares exact casefolded `(word, category)` pairs to the design inventory and makes a second invocation a no-op.

- [ ] **Step 4: Produce canonical source and registry**

Run append against `packs/en/core/function-words.jsonl`, then:

```powershell
python scripts/build_en_function_words.py --table packs/en/core/function-words.jsonl --registry packs/en/core/sense-ids.tsv --queue packs/en/trans-vi/review/function-words-expansion/queue-all.jsonl
```

Filter the 184 expansion source keys into `queue.jsonl`. Assert 327 function source keys, unchanged old 143 IDs, and 184 contiguous new IDs after the old maximum.

- [ ] **Step 5: Run green and commit**

```powershell
python -m unittest tests.test_build_en_function_words tests.test_append_en_function_words_expansion -v
git diff --check
```

Commit: `feat(core): add function word expansion source`.

### Task 2: Merge tagged grammar senses into the English core

**Files:**
- Modify: `scripts/merge_en_function_words_core.py`
- Modify: `tests/test_merge_en_function_words_core.py`
- Modify: `packs/en/core/data.jsonl`
- Modify: `packs/en/core/meta.json`

**Interface:** `merge_function_words_into_core(core_path, function_words_path, registry_path, meta_path=None) -> int` writes a `tags.register` list only for informal source rows, refreshes derived core metadata when `meta_path` is passed, and returns the source-row count.

- [ ] **Step 1: Write failing tests**

```python
def test_informal_source_sense_has_core_register_tag(tmp_path):
    merge_function_words_into_core(core, forms, registry, meta)
    assert sense_for(core, "gonna")["tags"] == {"register": ["informal"]}

def test_standard_source_sense_omits_register_tag(tmp_path):
    merge_function_words_into_core(core, forms, registry, meta)
    assert "tags" not in sense_for(core, "is")

def test_merge_refreshes_metadata_counts_and_checksum(tmp_path):
    merge_function_words_into_core(core, forms, registry, meta)
    assert json.loads(meta.read_text())["output"]["sha256"] == file_sha256(core)
```

- [ ] **Step 2: Run red**

Run: `python -m unittest tests.test_merge_en_function_words_core -v`

Expected: FAIL because register tags and metadata refresh are absent.

- [ ] **Step 3: Implement and merge real data**

Construct standard senses as `{id, pos}` and informal senses as `{id, pos, tags: {register: [informal]}}`. Do not remove existing sense keys. Recompute `records`, `senses`, `reserved_sense_ids`, `with_frequency`, `output.sha256`, and `output.bytes` after an atomic successful merge.

Run the real merger with the expanded table and core meta. Verify every 327 function ID appears once, all 184 new roles use the approved POS, and the core stays casefold-sorted.

- [ ] **Step 4: Run green and commit**

```powershell
python -m unittest tests.test_merge_en_function_words_core tests.test_build_core_en -v
python -m unittest discover -s tests -p "test_*.py" -v
git diff --check
```

Commit: `feat(core): merge expanded grammar senses`.

### Task 3: Prepare, submit, and validate one Luna rich-translation Batch

**Files:**
- Modify: `scripts/batch_trans_vi_luna_function_words.py`
- Modify: `tests/test_batch_trans_vi_luna_function_words.py`
- Modify: `scripts/merge_trans_vi_function_words.py`
- Modify: `tests/test_merge_trans_vi_function_words.py`
- Create ignored: `packs/en/trans-vi/review/function-words-expansion/queue.jsonl`
- Create ignored: `packs/en/trans-vi/review/function-words-expansion/input.jsonl`
- Create ignored: `packs/en/trans-vi/review/function-words-expansion/metadata.json`

**Interfaces:**
- Queues accept optional `register` and keep it in model input.
- `validate_rich_row(row, source)` accepts `adv`, requires informal wording for an informal source, and preserves all existing validation.
- `merge_function_words` accepts one exact combined 327-row rich batch and replaces only function-word IDs.

- [ ] **Step 1: Write failing tests**

Add `where` (`adv`) and `gonna` (`modal`, informal) source rows. Assert queue payload preserves register, then add:

```python
def test_accepts_adv_description_specific_to_question_form():
    assert validate_rich_row(valid_where_row, where_source) is None

def test_rejects_informal_source_without_informal_description():
    assert validate_rich_row(untagged_description_row, gonna_source) == "description must state informal register"
```

- [ ] **Step 2: Run red**

Run: `python -m unittest tests.test_batch_trans_vi_luna_function_words tests.test_merge_trans_vi_function_words -v`

Expected: FAIL because queue validation only accepts legacy fields and has no `adv`/informal source checks.

- [ ] **Step 3: Implement and produce exact Batch input**

Allow optional `register` queue rows, add `adv` description terms, and require informal wording when appropriate. Build exactly 184 source rows from `queue.jsonl` as at most 25 rows per request with `gpt-5.6-luna`, low reasoning, and low verbosity.

Assert 184 unique requested IDs, no old function IDs, and eight informal rows. Submit once using `.env`; never print the API key.

- [ ] **Step 4: Download, parse, and retry only missing IDs**

Poll Batch metadata until completed. Download and parse with `--allow-partial`; build retry inputs only for rejected/missing IDs. Repeat until exactly 184 rows validate. Keep artifacts ignored.

- [ ] **Step 5: Run green and commit code only**

Run focused parser/merge tests and `git diff --check`. Commit scripts/tests only: `feat(trans-vi): support expanded function words`.

### Task 4: Canonical merge and semantic audit

**Files:**
- Modify: `packs/en/trans-vi/data.jsonl`
- Modify: `packs/en/trans-vi/seed.jsonl`
- Modify: `packs/en/trans-vi/meta.json`

**Interface:** Existing 143 rich records plus 184 accepted rich rows form the exact 327-row input required by `merge_function_words`.

- [ ] **Step 1: Assemble exact rich coverage**

Extract the current 143 function-word rich records by registry ID; combine them with the 184 accepted rows; reject any ID duplicate or missing coverage before a canonical write.

- [ ] **Step 2: Merge and rebuild canonical artifacts**

Run `merge_trans_vi_function_words.py` with the 327-row combined JSONL, then run `build_trans_vi_canonical.py`. Validate 100% meanings coverage and unchanged rich fields for old 143 rows.

- [ ] **Step 3: Quality audit and targeted retry**

Inspect every informal row for its explicit label and all multi-role spellings: `as`, `than`, `nor`, `so`, `yet`, `there`, `when`, `however`. Sample at least 30 dispersed standard rows for natural Vietnamese, role-specific English descriptions, non-template examples, and collocations containing the input form. Any failed row goes to the targeted retry path before merge.

- [ ] **Step 4: Verify and commit**

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python -m json.tool packs/en/core/schema.json > $null
python -m json.tool packs/en/trans-vi/meta.json > $null
git diff --check
```

Commit: `feat(trans-vi): add expanded function word translations`.

