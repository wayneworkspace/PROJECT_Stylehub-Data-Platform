-- Câu hỏi: thời gian giao hàng trung bình, từ lúc gửi đến lúc nhận, theo bang (Buổi 5, Bài tập 2).
-- Chỉ tính lô đã có cả shipped_at và delivered_at.

CREATE OR REPLACE TABLE `${project}.${gold}.avg_delivery_days_by_state` AS
WITH delivered AS (
  SELECT
    u.state,
    TIMESTAMP_DIFF(s.delivered_at, s.shipped_at, HOUR) / 24 AS delivery_days
  FROM `${project}.${silver}.fact_shipments` AS s
  LEFT JOIN `${project}.${silver}.dim_users` AS u
    ON s.user_id = u.id
  WHERE s.shipped_at IS NOT NULL
    AND s.delivered_at IS NOT NULL
)
SELECT
  state,
  COUNT(*) AS n_shipments,
  AVG(delivery_days) AS avg_delivery_days
FROM delivered
GROUP BY state;
