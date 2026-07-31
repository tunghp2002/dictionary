# core-en

Pipeline tạo dữ liệu tiếng Anh dùng chung cho ứng dụng từ điển.

## Schema

Mỗi dòng trong `packs/en/core/data.jsonl` là một JSON object, dùng `word` làm key
trong IndexedDB:

```json
{
  "word": "heavy",
  "ipa": "/ˈhɛ.vi/",
  "level": "A1",
  "frequency": 1234,
  "senses": [
    { "id": 1000000000001, "pos": "adj" }
  ]
}
```

- `word`: lemma tiếng Anh.
- `ipa`: cách phát âm đầu tiên có trong Open English WordNet; bỏ qua nếu nguồn
  không có. Schema hiện chỉ cho phép một IPA.
- `level`: CEFR tổng quát (`A1`–`C2`), lấy mức thấp nhất nếu một từ xuất hiện
  ở nhiều POS/mức.
- `frequency`: thứ hạng tần suất trong chính tập `core-en`, `1` là phổ biến
  nhất. Chỉ ghi khi `wordfreq` có số liệu.
- `senses[].id`: số nguyên JavaScript-safe có namespace ngôn ngữ và được sắp
  tăng dần.
- `senses[].pos`: `noun`, `verb`, `adj` hoặc `adv`.

`core-en` không chứa nghĩa, ví dụ hay bản dịch tiếng Việt.

## Nguồn

- Open English WordNet 2025: lemma, POS, sense và IPA.
- CEFR-J Vocabulary Profile 1.5 + Octanove C1/C2 1.0: CEFR.
- wordfreq 3.1.1: tần suất.
- `trans-vi` hiện là seed thủ công, không phụ thuộc nguồn mở translation.

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
.venv/bin/python scripts/build_trans_vi_skeleton.py
```

Kết quả:

- `packs/en/core/data.jsonl`: dữ liệu để import vào IndexedDB.
- `packs/en/core/meta.json`: phiên bản nguồn, số lượng và SHA-256 của output.
- `packs/en/core/sense-ids.tsv`: registry nội bộ để ID không đổi giữa các lần build.
- `packs/en/trans-vi/data.jsonl`: toàn bộ sense English theo `sense_id`; sense
  chưa dịch là placeholder.
- `packs/en/trans-vi/seed.jsonl`: các record translation đã điền thủ công.
- `packs/en/trans-vi/meta.json`: số record đã điền, placeholder và checksum.

### English–Vietnamese curated target

`packs/en/trans-vi/target-manifest.json` chọn 30.000 lemma tiếng Anh có tần
suất cao nhất (thứ tự xác định), tương ứng 57.446 sense ID. Các mô tả
`description` là gloss tiếng Anh từ Open English WordNet trong hàng đợi review;
chúng cung cấp ngữ cảnh phân biệt nghĩa, không phải bản dịch. Bản dịch
`meaning` phải là nghĩa tiếng Việt ngắn gọn (tối đa 35 ký tự), không chứa chữ
Hán và không lặp lại toàn bộ gloss. Các batch đã duyệt trong
`packs/en/trans-vi/review/batches/` ghi đè record target theo `sense_id`, còn
ví dụ và collocation của record được giữ nguyên.

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

Không dùng `Common` vì core đã có `frequency`/`level`; không dùng `Technical`
vì quá chung. Tag tên kỳ thi (`IELTS`, `TOEFL`, `TOEIC`, `SAT`, ...) không
phải thuộc tính của sense. Nếu cần, mỗi kỳ thi sẽ là một collection có nguồn
riêng chứa danh sách `sense_id`; AI không tự đoán.

Translation pack chỉ chứa dữ liệu theo ngôn ngữ:

```json
{
  "sense_id": 1000000075634,
  "meaning": "nặng",
  "examples": [
    {"en": "This box is heavy.", "vi": "Cái hộp này nặng."}
  ],
  "collocations": ["heavy bag", "heavy suitcase"]
}
```

Khung hiện có toàn bộ `185.129` sense của core; `57.438` sense đã có
`meaning` (gồm seed thủ công và lượt DeepSeek đầu tiên), còn lại để
trống. `examples`/`collocations` sẽ fill ở phase sau cho nhóm từ phổ biến.
Khi fill thêm, cập nhật `seed.jsonl` rồi chạy `scripts/build_trans_vi_skeleton.py`;
không tạo ID mới ở translation.

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

Mỗi namespace có tối đa `999.999.999.999` sense. Namespace được giới hạn từ
`1` đến `999`, nên toàn bộ ID vẫn nằm trong miền số nguyên an toàn của
JavaScript.
