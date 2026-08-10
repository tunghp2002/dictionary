# Luna Batch Vietnamese Meaning Fill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate validated, concise Vietnamese meanings for all 57,446 target senses with `gpt-5.6-luna` using the OpenAI Batch API.

**Architecture:** A single standard-library Python CLI builds grouped Responses requests from the OEWN-only clean queue, uploads/submits/polls Batch jobs, parses structured outputs, and validates meaning-only JSONL. Existing merge/rebuild scripts apply only a complete validated output to the all-sense canonical files.

**Tech Stack:** Python standard library (`argparse`, `json`, `urllib`), OpenAI Responses/Batch API, existing `unittest` tests and trans-vi scripts.

## Global Constraints

- Use model ID `gpt-5.6-luna` verified through the account Models API.
- Read `OPENAI_API_KEY` from `.env` at runtime; never print it or commit it.
- Translate from only `sense_id`, `word`, `pos`, and OEWN `gloss`; do not use legacy Vietnamese data.
- Meanings must be natural Vietnamese, normally 1–5 words (six-word standard proper names allowed), at most 35 characters, and must not be truncated gloss fragments.
- Preserve every canonical `sense_id`; only `meaning` may change. Keep `description`, `examples`, and `collocations` empty.
- Store generated inputs/outputs under ignored `packs/en/trans-vi/review/` paths. Do not merge data before validation and pilot review.

---

### Task 1: Batch request builder and local output validator

**Files:**
- Create: `scripts/batch_trans_vi_luna_meanings.py`
- Create: `tests/test_batch_trans_vi_luna_meanings.py`

**Interfaces:**
- Consumes: JSONL rows with `sense_id`, `word`, `pos`, `gloss`.
- Produces: `build_requests(rows: list[dict], model: str, group_size: int) -> list[dict]` and `parse_output(path: Path, expected_ids: set[int]) -> tuple[list[dict], list[str]]`.
- Uses later: CLI subcommands `prepare`, `submit`, `status`, `download`, and `parse`.

- [ ] **Step 1: Write the failing test**

```python
def test_build_requests_keeps_each_group_and_uses_strict_schema(self):
    rows = [
        {"sense_id": 1, "word": "quick", "pos": "adjective", "gloss": ["moving fast"]},
        {"sense_id": 2, "word": "quick", "pos": "adjective", "gloss": ["alive"]},
    ]
    requests = build_requests(rows, "gpt-5.6-luna", 1)
    self.assertEqual([item["custom_id"] for item in requests], ["meaning-000001", "meaning-000002"])
    self.assertEqual(requests[0]["body"]["model"], "gpt-5.6-luna")
    self.assertTrue(requests[0]["body"]["text"]["format"]["strict"])
    self.assertIn('"sense_id":1', requests[0]["body"]["input"][-1]["content"][0]["text"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_batch_trans_vi_luna_meanings.BatchLunaMeaningTest.test_build_requests_keeps_each_group_and_uses_strict_schema`

Expected: FAIL because `scripts.batch_trans_vi_luna_meanings` does not exist.

- [ ] **Step 3: Write the failing parser-validation test**

```python
def test_parse_output_rejects_fragment_and_unknown_id(self):
    output = self.write_output({
        "custom_id": "meaning-000001",
        "response": {"status_code": 200, "body": {"output_text":
            '{"translations":[{"sense_id":1,"meaning":"được thực hiện với ít"},'
            '{"sense_id":99,"meaning":"nhanh"}]}'}}
    })
    rows, errors = parse_output(output, {1})
    self.assertEqual(rows, [])
    self.assertEqual(errors, [
        "meaning-000001: likely fragment for sense_id 1",
        "meaning-000001: unknown sense_id 99",
    ])
```

- [ ] **Step 4: Run parser test to verify it fails**

Run: `python -m unittest tests.test_batch_trans_vi_luna_meanings.BatchLunaMeaningTest.test_parse_output_rejects_fragment_and_unknown_id`

Expected: FAIL because `parse_output` does not exist.

- [ ] **Step 5: Write minimal implementation**

Create a standard-library CLI. `build_requests` must create JSONL Batch entries for `POST /v1/responses`, use a strict schema:

```python
{"type":"object","additionalProperties":False,
 "properties":{"translations":{"type":"array","items":{"type":"object","additionalProperties":False,
 "properties":{"sense_id":{"type":"integer"},"meaning":{"type":"string"}},
 "required":["sense_id","meaning"]}}},"required":["translations"]}
```

The request prompt must require exactly one record per input ID, natural Vietnamese word/phrase rather than a gloss translation, and explicitly reject incomplete phrases such as those ending in prepositions. Implement `validate_meaning` with all structural limits plus a small deterministic fragment list (leading/ending Vietnamese function words and the known bad pattern). The parser must collect all errors, return only fully valid records, and reject duplicate/unknown/missing IDs.

- [ ] **Step 6: Run local tests to verify they pass**

Run: `python -m unittest tests.test_batch_trans_vi_luna_meanings -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add scripts/batch_trans_vi_luna_meanings.py tests/test_batch_trans_vi_luna_meanings.py
git commit -m "feat(trans-vi): add Luna Batch meaning pipeline"
```

### Task 2: Generate and submit the bounded pilot

**Files:**
- Modify: `scripts/batch_trans_vi_luna_meanings.py`
- Generate (ignored): `packs/en/trans-vi/review/luna-meaning/pilot-input.jsonl`
- Generate (ignored): `packs/en/trans-vi/review/luna-meaning/pilot-batch.json`

**Interfaces:**
- Consumes: `scripts/build_trans_vi_clean_queue.py` output and CLI `prepare`.
- Produces: Batch ID in `pilot-batch.json`; pilot output downloaded into `pilot-output.jsonl`.

- [ ] **Step 1: Write the failing command-level test**

```python
def test_prepare_limits_pilot_and_writes_batch_jsonl(self):
    result = main(["prepare", "--queue", str(self.queue), "--output", str(self.output), "--limit", "3", "--group-size", "2"])
    self.assertEqual(result, 2)
    self.assertEqual(len(self.output.read_text(encoding="utf-8").splitlines()), 2)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m unittest tests.test_batch_trans_vi_luna_meanings.BatchLunaMeaningTest.test_prepare_limits_pilot_and_writes_batch_jsonl`

Expected: FAIL because the `prepare` command is not implemented.

- [ ] **Step 3: Implement and verify locally**

Implement `prepare` and API-only `submit`, `status`, and `download` commands. Use `urllib.request` with an `Authorization` header created in memory from `.env`. Upload input with `purpose=batch`, create with `endpoint=/v1/responses` and `completion_window=24h`, and write only non-secret Batch/file IDs and status metadata. Run the command-level test again; expected PASS.

- [ ] **Step 4: Create and submit pilot**

Run:

```bash
python scripts/build_trans_vi_clean_queue.py --output packs/en/trans-vi/review/luna-meaning/queue.jsonl
python scripts/batch_trans_vi_luna_meanings.py prepare --queue packs/en/trans-vi/review/luna-meaning/queue.jsonl --output packs/en/trans-vi/review/luna-meaning/pilot-input.jsonl --limit 500 --group-size 25
python scripts/batch_trans_vi_luna_meanings.py submit --input packs/en/trans-vi/review/luna-meaning/pilot-input.jsonl --metadata packs/en/trans-vi/review/luna-meaning/pilot-batch.json
```

Expected: 20 requests submitted using `gpt-5.6-luna`; canonical data unchanged.

- [ ] **Step 5: Poll, download, parse, and inspect**

After Batch status is `completed`, run `download` and `parse`. Require exactly 500 ordered, unique pilot IDs and zero parser errors. Inspect at least 30 records covering phrases, proper nouns, and multiple senses. If any meaning is a fragment or wrong sense, correct the prompt/validator and submit a replacement pilot; do not continue to Task 3.

- [ ] **Step 6: Commit**

```bash
git add scripts/batch_trans_vi_luna_meanings.py tests/test_batch_trans_vi_luna_meanings.py
git commit -m "feat(trans-vi): add Batch submission commands"
```

### Task 3: Submit, validate, and apply the full run

**Files:**
- Generate (ignored): `packs/en/trans-vi/review/luna-meaning/full-input.jsonl`
- Generate (ignored): `packs/en/trans-vi/review/luna-meaning/full-output.jsonl`
- Generate (ignored): `packs/en/trans-vi/review/luna-meaning/full-meanings.jsonl`
- Modify: `packs/en/trans-vi/data.jsonl`
- Modify: `packs/en/trans-vi/seed.jsonl`
- Modify: `packs/en/trans-vi/meta.json`

**Interfaces:**
- Consumes: validated pilot prompt and the complete clean queue.
- Produces: canonical all-sense data with complete target meaning coverage.

- [ ] **Step 1: Add failing merge coverage test**

```python
def test_merge_meanings_rejects_incomplete_target_coverage(self):
    with self.assertRaisesRegex(ValueError, "missing target sense"):
        merge_complete_meanings(self.batch, {1, 2}, self.seed, self.output)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m unittest tests.test_batch_trans_vi_luna_meanings.BatchLunaMeaningTest.test_merge_meanings_rejects_incomplete_target_coverage`

Expected: FAIL because the complete-coverage helper is not implemented.

- [ ] **Step 3: Implement and verify the complete-coverage guard**

Add a helper to the Batch script (or make a small checked wrapper around `merge_trans_vi_meanings.py`) that refuses to apply a full batch unless every target queue ID appears exactly once and has no parser error. Run the test again; expected PASS.

- [ ] **Step 4: Submit the remaining full Batch**

Use the accepted prompt and group size. Exclude pilot IDs already accepted, write the input and Batch metadata under `review/luna-meaning/`, submit, poll, and download. Validate all outputs before any merge.

- [ ] **Step 5: Apply only after full validation**

Merge accepted pilot and full records, run `build_trans_vi_meaning_only.py` to refresh the all-ID `data.jsonl`, `seed.jsonl`, and `meta.json`. Verify the 57,446 target IDs all have a meaning and every non-target `sense_id` remains present.

- [ ] **Step 6: Run regression checks**

Run:

```bash
python -m unittest tests.test_build_trans_vi_clean_queue tests.test_build_trans_vi_target tests.test_batch_trans_vi_luna_meanings tests.test_merge_trans_vi_clean_ai tests.test_validate_trans_vi_batches -v
python scripts/build_trans_vi_review_notes.py
git diff --check
```

Expected: all tests pass, no malformed JSONL, no non-target ID removal, and description/example/collocation counts remain zero.

- [ ] **Step 7: Commit**

```bash
git add scripts/batch_trans_vi_luna_meanings.py tests/test_batch_trans_vi_luna_meanings.py packs/en/trans-vi/data.jsonl packs/en/trans-vi/seed.jsonl packs/en/trans-vi/meta.json
git commit -m "feat(trans-vi): fill target Vietnamese meanings with Luna"
```
