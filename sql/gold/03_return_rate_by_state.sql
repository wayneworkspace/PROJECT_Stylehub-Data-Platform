-- Câu hỏi: tỷ lệ đơn bị trả lại (Returned) theo bang của khách (Buổi 5, Bài tập 2).

CREATE OR REPLACE TABLE `${project}.${gold}.return_rate_by_state` AS
WITH orders AS (
  SELECT o.id, o.status, u.state
  FROM `${project}.${silver}.fact_orders` AS o
  LEFT JOIN `${project}.${silver}.dim_users` AS u
    ON o.user_id = u.id
)
SELECT
  state,
  COUNT(*) AS n_orders,
  COUNTIF(status = 'Returned') AS n_returned,
  SAFE_DIVIDE(COUNTIF(status = 'Returned'), COUNT(*)) AS return_rate
FROM orders
GROUP BY state;
