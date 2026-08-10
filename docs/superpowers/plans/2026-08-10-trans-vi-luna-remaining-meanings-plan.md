# Luna Batch Remaining Vietnamese Meanings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill concise Vietnamese meanings for the 127,683 currently empty trans-vi senses using `gpt-5.6-luna` Batch requests.

**Architecture:** Add an OEWN-only remaining-queue builder that selects canonical records with an empty `meaning`. Reuse the existing strict Luna Batch pipeline with 50 senses per Responses request and 8,000-sense shards; parse partial results, retry only unresolved IDs, and merge only after exact coverage is proven.

**Tech Stack:** Python standard library, existing PyYAML OEWN loader, OpenAI Responses Batch API, `unittest`.

## Global Constraints

- Read only `sense_id`, `word`, `pos`, and OEWN glosses for model input; never reuse legacy Vietnamese text.
- Use `gpt-5.6-luna`, `reasoning.effort=low`, strict structured output, and Batch API `24h` jobs.
- Use 50 senses per API request and at most 8,000 senses per submitted Batch shard.
- Preserve every canonical sense ID; fill `meaning` only and keep rich fields empty.
- Accept compact official names and technical terms up to 50 characters and 12 words; reject malformed, duplicate, unknown, mojibake, CJK, and fragment output.
- Store all model input/output and metadata under ignored `packs/en/trans-vi/review/luna-remaining/` paths.
- Never merge a partial result into canonical data.

---

### Task 1: Build the OEWN-only remaining queue

**Files:**
- Create: `scripts/build_trans_vi_remaining_queue.py`
- Create: `tests/test_build_trans_vi_remaining_queue.py`

**Interfaces:**
- Consumes: `packs/en/core/sense-ids.tsv`, canonical trans-vi `data.jsonl`, and the OEWN YAML directory.
- Produces: `build_remaining_queue(registry_path: Path, data_path: Path, oewn_yaml: Path, output_path: Path) -> int`.
- Output rows have exactly `sense_id`, `word`, `pos`, and `gloss`, sorted by numeric `sense_id`.

- [ ] **Step 1: Write the failing selection test**

```python
def test_writes_only_empty_canonical_senses_with_oewn_context(self):
    # Registry and OEWN fixture contain alpha%1 and beta%1.
    # Canonical alpha has meaning "đầu tiên"; beta has meaning "".
    count = build_remaining_queue(registry, data, yaml_dir, output)
    self.assertEqual(count, 1)
    self.assertEqual(read_jsonl(output), [
        {"sense_id": 1000000000008, "word": "beta", "pos": "noun", "gloss": ["second gloss"]}
    ])
```

- [ ] **Step 2: Verify the test fails**

Run: `python -m unittest tests.test_build_trans_vi_remaining_queue -v`

Expected: import failure because the remaining-queue builder does not exist.

- [ ] **Step 3: Implement the small builder and CLI**

```python
def build_remaining_queue(registry_path, data_path, oewn_yaml, output_path):
    registry = load_id_registry(registry_path)
    existing = {int(row["sense_id"]): str(row.get("meaning", "")).strip()
                for row in read_jsonl(data_path)}
    if set(existing) != set(registry.values()):
        raise RuntimeError("canonical IDs and registry IDs differ")
    context = load_oewn_context(oewn_yaml)
    rows = []
    for source_key, sense_id in sorted(registry.items(), key=lambda item: item[1]):
        if existing.get(sense_id):
            continue
        item = context.get(source_key)
        if item is None:
            raise RuntimeError(f"Missing OEWN context for remaining sense {sense_id}")
        rows.append({"sense_id": sense_id, "word": item["word"], "pos": item["pos"], "gloss": item["definitions"]})
    write_jsonl(output_path, rows)
    return len(rows)
```

Expose `--registry`, `--data`, `--oewn-yaml`, and `--output` arguments. Validate that every canonical ID appears in the registry and that each generated row has at least one gloss.

- [ ] **Step 4: Verify green and commit**

Run:

```powershell
python -m unittest tests.test_build_trans_vi_remaining_queue tests.test_build_trans_vi_clean_queue -v
git add scripts/build_trans_vi_remaining_queue.py tests/test_build_trans_vi_remaining_queue.py
git commit -m "feat(trans-vi): queue remaining OEWN senses"
```

### Task 2: Allow a retry queue with no recovered records

**Files:**
- Modify: `scripts/batch_trans_vi_luna_meanings.py`
- Modify: `tests/test_batch_trans_vi_luna_meanings.py`

**Interfaces:**
- Changes `build_retry_queue(source_paths: list[Path], accepted_paths: list[Path] | None = None) -> list[dict]`.
- The `retry-queue` CLI accepts one or more `--source` files and zero or more `--accepted` files.

- [ ] **Step 1: Write the failing CLI test**

```python
def test_retry_queue_allows_no_recovered_files(self):
    source.write_text(two_clean_queue_rows, encoding="utf-8")
    result = main(["retry-queue", "--source", str(source), "--output", str(output)])
    self.assertEqual(result, 2)
    self.assertEqual(read_jsonl(output), two_clean_queue_rows)
```

- [ ] **Step 2: Verify red**

Run: `python -m unittest tests.test_batch_trans_vi_luna_meanings.BatchLunaMeaningTest.test_retry_queue_allows_no_recovered_files -v`

Expected: `argparse` rejects the missing required `--accepted` argument.

- [ ] **Step 3: Implement the default**

Give `build_retry_queue` a `None` default that is treated as an empty list and change
`retry_queue.add_argument("--accepted", action="append", type=Path)` to omit
`required=True`. Continue rejecting malformed source or accepted rows when an
accepted file is supplied.

- [ ] **Step 4: Verify green and commit**

```powershell
python -m unittest tests.test_batch_trans_vi_luna_meanings -v
git add scripts/batch_trans_vi_luna_meanings.py tests/test_batch_trans_vi_luna_meanings.py
git commit -m "fix(trans-vi): allow initial retry queue"
```

### Task 3: Generate budgeted Batch shards

**Files:**
- Generate (ignored): `packs/en/trans-vi/review/luna-remaining/queue.jsonl`
- Generate (ignored): `packs/en/trans-vi/review/luna-remaining/shard-001-input.jsonl` through `shard-016-input.jsonl`
- Generate (ignored): matching `shard-XXX-batch.json` metadata files

**Interfaces:**
- Consumes: Task 1 queue and the existing `batch_trans_vi_luna_meanings.py prepare` and `submit` commands.
- Produces: 16 independently resumable Batch shards: fifteen 8,000-sense shards and one 7,683-sense shard.

- [ ] **Step 1: Build and verify the queue**

```powershell
python scripts/build_trans_vi_remaining_queue.py `
  --registry packs/en/core/sense-ids.tsv `
  --data packs/en/trans-vi/data.jsonl `
  --oewn-yaml .cache/sources/oewn-2025/src/yaml `
  --output packs/en/trans-vi/review/luna-remaining/queue.jsonl
```

Verify the output contains exactly 127,683 rows, no existing filled ID, and only the four queue fields.

- [ ] **Step 2: Create all 16 inputs with the cost-saving group size**

Run `prepare` once per shard with `--group-size 50`; use offsets `0, 8000, …, 112000` and limits `8000` for shards 001–015, then offset `120000` and limit `7683` for shard 016. Each full shard must contain 160 requests and the final shard 154 requests.

```powershell
python scripts/batch_trans_vi_luna_meanings.py prepare `
  --queue packs/en/trans-vi/review/luna-remaining/queue.jsonl `
  --output packs/en/trans-vi/review/luna-remaining/shard-001-input.jsonl `
  --offset 0 --limit 8000 --group-size 50 --model gpt-5.6-luna
```

- [ ] **Step 3: Submit at most two shards concurrently**

Submit shards 001 and 002 first with `submit --env .env`; write their metadata separately. Once either reaches a terminal state, submit the next unsent shard. This caps enqueued input below the prior account-limit failure while avoiding idle time.

- [ ] **Step 4: Record the initial usage/checkpoint**

For every terminal status, retain its metadata with `request_counts` and `usage` so final token usage can be reported. Do not expose the API key.

### Task 4: Parse terminal results and retry only residual IDs

**Files:**
- Generate (ignored): `shard-XXX-output.jsonl`, `shard-XXX-meanings.jsonl`, and `shard-XXX-retry.jsonl`
- Generate (ignored): `retry-round-N-queue.jsonl`, input, metadata, output, and meanings files

**Interfaces:**
- Consumes: terminal Batch metadata and queue slices from Task 3.
- Produces: one meaning-only JSONL per accepted shard plus an exact retry queue.

- [ ] **Step 1: Download every terminal output**

Use `download` for both `completed` and `cancelled` metadata. The existing downloader accepts a cancelled Batch only when `output_file_id` is present.

```powershell
python scripts/batch_trans_vi_luna_meanings.py download `
  --metadata packs/en/trans-vi/review/luna-remaining/shard-001-batch.json `
  --output packs/en/trans-vi/review/luna-remaining/shard-001-output.jsonl --env .env
```

- [ ] **Step 2: Parse while preserving valid siblings**

For each shard, run `parse --allow-partial --retry-queue` against the same offset and limit used to prepare it. Store accepted `sense_id`/`meaning` rows and the source rows still needing a retry.

- [ ] **Step 3: Assemble and submit the residual queue**

Use the existing `retry-queue` command with all shard retry queues as
`--source` and no `--accepted` value to construct the first residual queue.
For later rounds, pass the previous-round retry queue as `--source` and each
accepted retry-meaning file as `--accepted`. Submit residuals in 8,000-sense
groups with 50 senses per request. Repeat until the retry queue has zero lines.

- [ ] **Step 4: Audit quality before merge**

For the complete accepted set, assert no mojibake/CJK, each meaning passes `validate_meaning`, and inspect evenly distributed samples plus every meaning over five words. Do not rerun valid senses because a sibling failed.

### Task 5: Apply, verify, and integrate

**Files:**
- Modify: `packs/en/trans-vi/data.jsonl`
- Modify: `packs/en/trans-vi/seed.jsonl`
- Modify: `packs/en/trans-vi/meta.json`
- Modify: `packs/en/trans-vi/notes-review.jsonl`

**Interfaces:**
- Consumes: every accepted Task 4 meaning file and the remaining queue’s expected IDs.
- Produces: full canonical coverage: 185,129 meanings, 185,129 IDs, and empty rich fields.

- [ ] **Step 1: Prove exact remaining coverage before mutation**

```python
expected = {row["sense_id"] for row in read_jsonl(remaining_queue)}
rows = [row for path in accepted_paths for row in read_jsonl(path)]
require_complete_coverage(rows, expected)
```

Also assert `validate_meaning(row["meaning"]) is None` for every row.

- [ ] **Step 2: Merge then rebuild canonical files**

```powershell
python scripts/merge_trans_vi_meanings.py --data packs/en/trans-vi/data.jsonl --batch <each-accepted-path>
python scripts/build_trans_vi_meaning_only.py `
  --source packs/en/trans-vi/data.jsonl --data packs/en/trans-vi/data.jsonl `
  --seed packs/en/trans-vi/seed.jsonl --meta packs/en/trans-vi/meta.json
python scripts/build_trans_vi_review_notes.py
```

- [ ] **Step 3: Run final verification**

```powershell
$modules = Get-ChildItem tests -Filter 'test_*.py' | Sort-Object Name | ForEach-Object { 'tests.' + $_.BaseName }
python -m unittest @modules -v
git diff --check
```

Use a Python audit to require 185,129 unique IDs, 185,129 nonempty meanings, zero nonempty descriptions/examples/collocations, and a metadata checksum matching `data.jsonl`.

- [ ] **Step 4: Commit, merge, and push**

```powershell
git add packs/en/trans-vi scripts/build_trans_vi_remaining_queue.py tests/test_build_trans_vi_remaining_queue.py
git commit -m "feat(trans-vi): fill remaining Luna meanings"
git push origin dev
```
