# Dictionary packs

Mỗi thư mục con là một pack độc lập:

- `core`: kiến thức chung của ngôn ngữ nguồn.
- `trans-xx`: dữ liệu dịch sang ngôn ngữ `xx`, tham chiếu `sense_id` của core.

Grammar, expression type, register, usage, region và domain nằm trong `core`.
Translation chỉ chứa meaning, examples và collocations của ngôn ngữ đích.
Danh sách phục vụ kỳ thi là collection riêng, không phải tag của sense.

Pack chưa có dữ liệu được giữ bằng `.gitkeep`; không tạo bản dịch giả.
