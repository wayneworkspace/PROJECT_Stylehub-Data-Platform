-- Rule nghiệp vụ: tính mọi đơn trừ Cancelled (Buổi 3). Mỗi ngày một dòng.

CREATE OR REPLACE TABLE `${project}.${gold}.daily_revenue` AS
WITH valid_orders AS (
  SELECT order_date, total_amount
  FROM `${project}.${silver}.fact_orders`
  WHERE status != 'Cancelled'
)
SELECT
  order_date,
  COUNT(*) AS n_orders,
  SUM(total_amount) AS revenue
FROM valid_orders
GROUP BY order_date;
