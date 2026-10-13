-- Tổng revenue ở Gold phải bằng tổng total_amount (không Cancelled) ở Silver.

WITH gold AS (
  SELECT SUM(revenue) AS total
  FROM `${project}.${gold}.daily_revenue`
),
silver AS (
  SELECT SUM(total_amount) AS total
  FROM `${project}.${silver}.fact_orders`
  WHERE status != 'Cancelled'
)
SELECT
  gold.total AS gold_total,
  silver.total AS silver_total
FROM gold
CROSS JOIN silver
WHERE gold.total != silver.total;
