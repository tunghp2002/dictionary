# Luna Batch Remaining Vietnamese Meanings Design

## Goal

Fill a concise Vietnamese `meaning` for every currently empty trans-vi sense,
while preserving all 185,129 canonical sense IDs and leaving rich fields empty.

## Scope

- Source only `sense_id`, `word`, `pos`, and glosses from OEWN.
- Select only canonical records whose `meaning` is empty at queue-build time.
- Do not fill `description`, `examples`, or `collocations`.
- Retain the existing 57,446 validated meanings without sending them to the API.

## Batch Strategy

1. Build a stable OEWN-only queue for the remaining 127,683 senses.
2. Use `gpt-5.6-luna` with `reasoning.effort=low` and strict JSON output.
3. Put 50 senses in each Responses request to halve repeated prompt overhead
   compared with the earlier 25-sense grouping.
4. Submit no more than 8,000 senses per Batch shard. This stays beneath the
   proven account queue envelope even when rare senses have longer glosses.
5. Parse every terminal output, including partial output from cancelled Batches.
   Write a retry queue containing only missing or rejected sense IDs.
6. Retry only the residual queue, then require exact complete coverage before
   touching canonical data.

## Quality Rules

- Meanings are natural Vietnamese dictionary headwords, normally 1–5 words.
- Technical terms and official names may be up to 50 characters and 12 words
  when shortening would make them unclear.
- Reject malformed JSON, duplicate or unknown IDs, CJK leakage, mojibake, and
  known gloss-fragment patterns.
- Inspect dispersed samples and all long accepted meanings before merge.

## Canonical Apply

After coverage validation, merge the new meanings into `data.jsonl`, rebuild
`seed.jsonl` and `meta.json`, and confirm all 185,129 IDs remain. The only
nonempty generated field is `meaning`.

## Verification

- Unit-test the remaining-queue builder and shard boundaries before API calls.
- Run the full repository test modules after merge.
- Verify exact target coverage, Unicode integrity, empty rich-field counts,
  stable ID count, and matching metadata checksum.
