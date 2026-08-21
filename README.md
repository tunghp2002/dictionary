# core-en

A reproducible English–Vietnamese dictionary-data pipeline. It builds a shared
English core indexed by headword and a Vietnamese translation pack indexed by
stable sense ID. The current snapshot contains **128,239 headwords** and
**185,553 English senses**; every English sense has a Vietnamese meaning.

## Data model

Each line of `packs/en/core/data.jsonl` is one JSON object keyed by `word`,
which makes it suitable for direct import into IndexedDB or another
headword-keyed store.

```json
{
  "word": "heavy",
  "ipa": "/ˈhɛ.vi/",
  "frequency": 1234,
  "senses": [
    {"id": 1000000000001, "pos": "adj"}
  ]
}
```

- `word` is the English lemma or expression.
- `ipa` is the first pronunciation available in Open English WordNet; it is
  omitted when the source has none.
- `frequency` is a rank within this core: `1` is most frequent. It is present
  only when `wordfreq` provides a score.
- `senses[].id` is a JavaScript-safe, stable integer.
- `senses[].pos` uses the controlled POS vocabulary in
  `packs/en/core/schema.json` (for example `noun`, `verb`, `adj`, `adv`,
  `pronoun`, `preposition`, and `interjection`).
- A sense may also contain `grammar`, `synonyms`, `antonyms`,
  `expression_type`, and `tags`. Empty optional fields are omitted to keep the
  JSONL compact.

The core deliberately has no unproven proficiency or exam-level field.

### Pack relationship

| Pack | Key | Contents |
| --- | --- | --- |
| `packs/en/core/` | `word` | English headwords, senses, lexical metadata, and optional learning notes |
| `packs/en/trans-vi/` | `sense_id` | Vietnamese meanings plus English descriptions, examples, and collocations |

The client resolves a definition by reading a core record and then looking up
each of its sense IDs in `trans-vi`. This separation lets translations be
updated without changing English sense IDs.

## Learning notes

An optional `learning` field is embedded directly in the relevant core record.
It contains concise Vietnamese study guidance and is not an official exam-word
list.

```json
{
  "word": "increase",
  "senses": [{"id": 1000000000123, "pos": "verb"}],
  "learning": {
    "grammar_patterns": [
      {"pattern": "increase by + amount", "vi": "tăng thêm bao nhiêu"}
    ],
    "word_family": [{"word": "increasing"}],
    "usage_notes": [],
    "confusables": [{"word": "rise", "vi": "rise thường không có tân ngữ"}]
  }
}
```

`word_family` is a reference only: every item points to a different, existing
headword in the same core. It never repeats a POS, Vietnamese meaning, or a
sense ID. The application follows that link to retrieve the target word's
current senses and translations from the same datasets.

`scripts/batch_learning_vi.py` creates notes only for headwords without a
`learning` field. Its merge step removes self-links, duplicate links, and links
to headwords that do not exist in the core.

## English–Vietnamese translations

`packs/en/trans-vi/data.jsonl` is the canonical Vietnamese translation dataset.
Each row contains a concise Vietnamese `meaning` and the English OEWN gloss as
`description`. `examples` and `collocations` are included only when they pass
the project's structural and quality checks.

```json
{
  "sense_id": 1000000075634,
  "meaning": "nặng",
  "description": "of comparatively great physical weight or density",
  "examples": [
    {"en": "This box is heavy.", "vi": "Cái hộp này nặng."}
  ],
  "collocations": ["heavy bag", "heavy suitcase"]
}
```

All **185,553** current core senses have a Vietnamese meaning. Translation and
learning content is machine-generated, then checked by deterministic project
validators; it has not received comprehensive human editorial review or a
formal human benchmark. Keep `sense_id` unchanged when editing translations,
then run `scripts/build_trans_vi_canonical.py` to synchronize `data.jsonl`,
`seed.jsonl`, and metadata.

## Sources and attribution

- [Open English WordNet 2025](https://en-word.net/): headwords, parts of
  speech, senses, lexical relations, and IPA where available. The exact source
  revision is pinned in `packs/en/core/meta.json`.
- [wordfreq 3.1.1](https://github.com/rspeer/wordfreq): frequency ranks.
- OpenAI Batch API: Vietnamese translations and learning-note enrichment,
  subject to the validation described above.

Source snapshots are pinned by `scripts/fetch_sources.py`. See
[DATA_LICENSES.md](DATA_LICENSES.md) and [NOTICE.md](NOTICE.md) for full
attribution and third-party terms.

## Repository layout

```text
packs/
├── en/
│   ├── core/
│   ├── trans-vi/
│   ├── trans-zh/
│   └── trans-ja/
├── zh/
│   ├── core/
│   ├── trans-vi/
│   └── trans-en/
└── ja/
    ├── core/
    └── trans-vi/
```

Each pack may contain `data.jsonl` and `meta.json`. The English core also has
`sense-ids.tsv`, the registry that reserves issued IDs. The populated public
data is currently in `packs/en/core/` and `packs/en/trans-vi/`.

## Build

Requires Python 3.11+.

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-build.txt
.venv/bin/python scripts/fetch_sources.py
.venv/bin/python scripts/build_core_en.py
.venv/bin/python scripts/merge_en_function_words_core.py
.venv/bin/python scripts/build_trans_vi_canonical.py
```

Build outputs:

- `packs/en/core/data.jsonl`: core data for a headword-keyed store.
- `packs/en/core/meta.json`: source revisions, counts, and output checksum.
- `packs/en/core/sense-ids.tsv`: stable internal sense-ID registry.
- `packs/en/trans-vi/data.jsonl`: Vietnamese data for every English sense.
- `packs/en/trans-vi/seed.jsonl`: canonical input used to rebuild the
  translation pack.
- `packs/en/trans-vi/meta.json`: translation coverage, counts, and checksum.

Run the test suite with:

```bash
.venv/bin/python -m unittest discover -s tests
```

## Sense IDs

Sense IDs use this format:

```text
namespace × 10^12 + local_id
```

- English uses namespace `1`: `1000000000001`, `1000000000002`, and so on.
- Other language cores receive namespaces `2`, `3`, and so on.
- Translation rows for the English core always reference namespace `1`; a
  Vietnamese translation never creates a new namespace.
- Issued IDs remain reserved in `sense-ids.tsv` and are never reused, even if
  a source sense disappears.

A namespace supports up to `999,999,999,999` senses. Namespaces `1` through
`999` keep every ID within JavaScript's safe-integer range.

## License

- Code, scripts, tests, schemas, and documentation: [Apache-2.0](LICENSE).
- Dataset files under `packs/`, except schemas: [CC BY-SA 4.0](LICENSE-DATA.md).
- Third-party attribution and licensing: [NOTICE.md](NOTICE.md) and
  [DATA_LICENSES.md](DATA_LICENSES.md).

Derived dataset files must retain attribution, state changes, and remain under
CC BY-SA 4.0. Apache-2.0 continues to apply to schema files, not to the other
dataset files in `packs/`.
