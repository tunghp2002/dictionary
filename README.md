# core-en

Pipeline tạo dữ liệu tiếng Anh dùng chung cho ứng dụng từ điển.

## Schema

Mỗi dòng trong `packs/en/core/data.jsonl` là một JSON object, dùng `word` làm key
trong IndexedDB:

```json
{
  "word": "heavy",
  "ipa": "/ˈhɛ.vi/",
  "frequency": 1234,
  "senses": [
    { "id": 1000000000001, "pos": "adj" }
  ]
}
```

- `word`: lemma tiếng Anh.
- `ipa`: cách phát âm đầu tiên có trong Open English WordNet; bỏ qua nếu nguồn
  không có. Schema hiện chỉ cho phép một IPA.
- `frequency`: thứ hạng tần suất trong chính tập `core-en`, `1` là phổ biến
  nhất. Chỉ ghi khi `wordfreq` có số liệu.
- `senses[].id`: số nguyên JavaScript-safe có namespace ngôn ngữ và được sắp
  tăng dần.
- `senses[].pos`: `noun`, `verb`, `adj` hoặc `adv`.
- `senses[].synonyms` và `senses[].antonyms`: quan hệ theo đúng synset/sense
  của Open English WordNet; bỏ field nếu nguồn không có quan hệ.
- `level` hiện được chủ động bỏ khỏi schema và public build vì chưa có nguồn
  phân loại đủ rõ quyền tái phân phối.

`core-en` không chứa nghĩa, ví dụ hay bản dịch tiếng Việt.

## Nguồn

- Open English WordNet 2025: lemma, POS, sense và IPA.
- wordfreq 3.1.1: tần suất.
- `trans-vi` dùng ngữ cảnh sense của Open English WordNet để tạo meaning tiếng
  Việt, description tiếng Anh, ví dụ song ngữ và collocation. Nội dung được tạo
  bằng OpenAI Batch API rồi phải vượt qua các kiểm tra cấu trúc và chất lượng
  xác định của dự án.

Các snapshot được ghim phiên bản trong `scripts/fetch_sources.py`. Xem điều
khoản và attribution tại [DATA_LICENSES.md](DATA_LICENSES.md).

## Pack layout

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

Mỗi pack có thể chứa `data.jsonl` và `meta.json`; `core` có thêm registry
`sense-ids.tsv`. Hiện dữ liệu thật có trong `packs/en/core/` và
`packs/en/trans-vi/`.

## Build

Yêu cầu Python 3.11+:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-build.txt
.venv/bin/python scripts/fetch_sources.py
.venv/bin/python scripts/build_core_en.py
.venv/bin/python scripts/merge_en_function_words_core.py
.venv/bin/python scripts/build_trans_vi_canonical.py
```

Kết quả:

- `packs/en/core/data.jsonl`: dữ liệu để import vào IndexedDB.
- `packs/en/core/meta.json`: phiên bản nguồn, số lượng và SHA-256 của output.
- `packs/en/core/sense-ids.tsv`: registry nội bộ để ID không đổi giữa các lần build.
- `packs/en/trans-vi/data.jsonl`: toàn bộ sense English theo `sense_id`; sense
  chưa dịch là placeholder.
- `packs/en/trans-vi/seed.jsonl`: bản sao nguồn canonical dùng để tái build pack.
- `packs/en/trans-vi/meta.json`: số record đã điền, placeholder và checksum.

### English–Vietnamese canonical data

`packs/en/trans-vi/data.jsonl` là dataset canonical cho toàn bộ sense ID tiếng
Anh. Mỗi `meaning` là nghĩa tiếng Việt ngắn gọn; `description` là mô tả tiếng
Anh theo gloss OEWN của sense. Ví dụ và collocation chỉ được giữ khi vượt qua
validator của dự án (schema, ngôn ngữ, dấu câu, headword và các mẫu placeholder
hoặc ghi chú biên tập). Đây là kiểm định tự động, không phải tuyên bố rằng toàn
bộ 185.456 sense đã được con người duyệt. Các hàng đợi review và batch không
thuộc repository.

Core sense dùng schema chung. Các trường metadata rỗng được bỏ khỏi JSONL để
giảm kích thước:

```json
{
  "id": 1000000075634,
  "pos": "verb",
  "expression_type": "phrasal_verb",
  "grammar": {
    "verb_type": ["transitive", "intransitive"]
  },
  "tags": {
    "register": ["informal"],
    "usage": [],
    "region": ["GB"],
    "domains": []
  }
}
```

- `grammar.countability`: `countable`, `uncountable`.
- `grammar.verb_type`: `transitive`, `intransitive`, `linking`.
- `expression_type`: `compound`, `phrasal_verb`, `idiom`; bỏ field với từ đơn.
- `tags.register`: `formal`, `informal`, `slang`, `literary`, `vulgar`.
- `tags.usage`: `archaic`, `dated`, `derogatory`, `euphemistic`, `figurative`,
  `humorous`, `offensive`, `rare`.
- `tags.region`: mã vùng `AU`, `CA`, `GB`, `IE`, `IN`, `NZ`, `US`, `ZA`.
- `tags.domains`: tối đa hai domain trong enum của
  `packs/en/core/schema.json`.

Không dùng `Common` vì core đã có `frequency`; không dùng `Technical`
vì quá chung. Tag tên kỳ thi (`IELTS`, `TOEFL`, `TOEIC`, `SAT`, ...) không
phải thuộc tính của sense. Nếu cần, mỗi kỳ thi sẽ là một collection có nguồn
riêng chứa danh sách `sense_id`; AI không tự đoán.

Translation pack chỉ chứa dữ liệu theo ngôn ngữ:

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

Khung hiện có `185.456` sense của core và đã có meaning tiếng Việt cho tất
cả. Khi cập nhật bản dịch, giữ nguyên `sense_id` rồi chạy
`scripts/build_trans_vi_canonical.py` để đồng bộ `data.jsonl`, `seed.jsonl` và metadata.

Kiểm thử:

```bash
.venv/bin/python -m unittest discover -s tests
```

## Sense ID

ID dùng format:

```text
namespace × 10^12 + local_id
```

- English có namespace `1`: `1000000000001`, `1000000000002`, ...
- Một core ngôn ngữ khác sẽ nhận namespace `2`, `3`, ...
- Translation của core English luôn tham chiếu ID namespace `1`; bản dịch
  tiếng Việt không tự tạo ID namespace mới.
- ID đã cấp được lưu trong registry và không tái sử dụng, kể cả khi sense bị
  xóa khỏi nguồn.

## License

- Code, scripts, tests, schemas và tài liệu: Apache-2.0, xem `LICENSE`.
- Các file dataset trong `packs/` (trừ schema): CC BY-SA 4.0, xem
  `LICENSE-DATA.md`.
- Attribution và điều khoản nguồn bên thứ ba: `NOTICE.md` và
  `DATA_LICENSES.md`.

Các file dữ liệu phái sinh phải giữ attribution, nêu rõ thay đổi và tiếp tục
dùng CC BY-SA 4.0. License Apache-2.0 vẫn áp dụng cho các file schema; không áp
dụng cho các file dataset khác trong `packs/`.

Mỗi namespace có tối đa `999.999.999.999` sense. Namespace được giới hạn từ
`1` đến `999`, nên toàn bộ ID vẫn nằm trong miền số nguyên an toàn của
JavaScript.
