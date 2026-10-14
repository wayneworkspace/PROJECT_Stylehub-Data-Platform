-- Total revenue in Gold must equal the total total_amount (excluding Cancelled) in Silver.
-- Tagged gold because it needs daily_revenue, so it runs in the gold step.
{{ config(tags=['gold']) }}

WITH gold AS (
  SELECT SUM(revenue) AS total
  FROM {{ ref('daily_revenue') }}
),
silver AS (
  SELECT SUM(total_amount) AS total
  FROM {{ ref('fact_orders') }}
  WHERE status != 'Cancelled'
)
SELECT
  gold.total AS gold_total,
  silver.total AS silver_total
FROM gold
CROSS JOIN silver
WHERE gold.total != silver.total
