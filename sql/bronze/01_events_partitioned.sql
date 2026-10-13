-- Buổi 1: bảng events (~108 triệu dòng) partition theo ngày, cluster theo event_type, product_id.
-- Chạy tay một lần (quét toàn bảng nguồn), không nằm trong chạy hằng ngày.
-- ${source} là dataset chứa bảng events gốc của khóa học (mặc định stylehub).
-- Nếu query theo user_id là phổ biến, cân nhắc thêm user_id vào CLUSTER BY (xem docs/DECISIONS.md).

CREATE OR REPLACE TABLE `${project}.${bronze}.events_partitioned`
PARTITION BY DATE(event_time)
CLUSTER BY event_type, product_id
AS
SELECT *
FROM `${project}.${source}.events`;
