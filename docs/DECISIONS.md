# Quyết định thiết kế

Ghi mỗi quyết định kèm số liệu đo thật. Đây là chỗ trả lời câu hỏi phỏng vấn "vì sao chọn cách này".

## 1. Partition và cluster cho `events` (Buổi 1)

Hiện tại: `PARTITION BY DATE(event_time) CLUSTER BY event_type, product_id`.

| Query | Bytes processed | Tận dụng partition/cluster |
|---|---|---|
| Top 10 sản phẩm purchase trong 1 tuần | _điền sau khi đo_ | partition + cluster |
| Đếm event theo event_type trong 1 ngày | _điền_ | partition |
| Toàn bộ lịch sử của 1 user_id (không lọc ngày) | _điền_ | không |

Nếu query theo `user_id` là phổ biến: thêm `user_id` vào cluster key, vì BigQuery chỉ bỏ qua block khi WHERE có cột cluster. Ghi số đo trước và sau khi đổi.

## 2. Watermark cho `order_items` (Buổi 2)

_Điền sau khi kiểm tra: khi đơn đổi trạng thái, `updated_at` của `order_items` có đổi không? Chọn cột và lookback dựa trên kết quả._

README ngắn trả lời 3 câu: vì sao chọn cột đó và lookback bao nhiêu ngày; chạy lại thì Raw Zone có gì và bỏ dòng trùng bằng cách nào; nguồn xóa một dòng thì pipeline có biết không.

## 3. Sync mode từng bảng (Buổi 4)

_Điền theo bảng ở ARCHITECTURE.md, mỗi bảng một câu giải thích và số dòng so với nguồn._

## 4. Star hay Snowflake (Buổi 5)

Chọn Star (mặc định). Chuyển Snowflake chỉ khi dimension rất lớn, nhiều tầng, thuộc tính đổi thường xuyên.
