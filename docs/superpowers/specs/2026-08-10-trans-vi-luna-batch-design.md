# Luna Batch Vietnamese Meaning Fill

## Goal

Fill a concise, natural Vietnamese `meaning` for each of the 57,446 target
senses in the 30,000-word English target. Preserve every existing `sense_id`.
Leave `description`, `examples`, and `collocations` empty.

## Approach

Use `gpt-5.6-luna` through the OpenAI Batch API and the Responses endpoint.
Each Batch request contains a small, ordered group of OEWN-only records
(`sense_id`, `word`, `pos`, `gloss`) and must return strict JSON containing the
same IDs and one Vietnamese meaning per ID. The model is instructed to choose
the sense indicated by the gloss; it must not mechanically translate or cut
off the gloss.

## Execution

1. Build the clean 57,446-sense queue from OEWN source data.
2. Submit a 500-sense pilot Batch, grouped into 25-sense requests to reduce
   prompt repetition while keeping responses auditable.
3. Parse and reject malformed, unknown, duplicate, empty, overlong,
  non-Vietnamese, or likely-fragment meanings. Meanings normally use one to
  five words; standard six-word Vietnamese proper names are accepted.
  Spot-check accepted pilot
   entries, especially multi-sense and phrase entries.
4. If the pilot passes, submit the remaining senses in one Batch using the
   same prompt and validation.
5. Merge only validated `{sense_id, meaning}` records into the all-ID table,
   regenerate `seed.jsonl` and `meta.json`, run repository tests, then commit.

## Safety and Cost Controls

- `.env` supplies the API key only at runtime and is gitignored.
- Batch source and outputs stay in ignored review storage.
- Structured JSON prevents ID drift; no original record is changed before
  validation succeeds.
- Batch processing receives OpenAI's discounted asynchronous pricing. The
  output is limited to a short meaning and no descriptions/examples.

## Failure Handling

Failed or rejected groups are written to a retry queue. They are never merged
automatically. A completed pilot with unacceptable semantic quality blocks the
full Batch so its prompt can be corrected first.
