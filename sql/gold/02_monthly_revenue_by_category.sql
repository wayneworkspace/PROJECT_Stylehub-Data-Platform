-- Câu hỏi: doanh thu và lợi nhuận theo category mỗi tháng (Buổi 5, Bài tập 1).
-- Rule ở Gold: bỏ đơn Cancelled, lợi nhuận = amount - total_cost.

CREATE OR REPLACE TABLE `${project}.${gold}.monthly_revenue_by_category` AS
WITH valid_orders AS (
  SELECT id AS order_id
  FROM `${project}.${silver}.fact_orders`
  WHERE status != 'Cancelled'
),
items AS (
  SELECT i.*
  FROM `${project}.${silver}.fact_order_items` AS i
  INNER JOIN valid_orders USING (order_id)
)
SELECT
  DATE_TRUNC(DATE(i.created_at), MONTH) AS month,
  p.category,
  SUM(i.amount) AS revenue,
  SUM(i.amount - i.total_cost) AS profit
FROM items AS i
INNER JOIN `${project}.${silver}.dim_products` AS p
  ON i.product_id = p.id
GROUP BY month, p.category;
