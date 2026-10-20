-- Gold revenue totals must equal Silver; a returned row fails.
{{ config(tags=['pg_gold']) }}

WITH silver AS (
  SELECT SUM(amount) AS revenue
  FROM {{ ref('pg_fact_order_items') }}
  WHERE {{ pg_revenue_filter('status') }}
),

daily AS (
  SELECT SUM(revenue) AS revenue
  FROM {{ ref('pg_daily_revenue') }}
),

monthly AS (
  SELECT SUM(revenue) AS revenue
  FROM {{ ref('pg_monthly_revenue_by_category') }}
)

SELECT
  s.revenue AS silver_revenue,
  d.revenue AS daily_revenue,
  m.revenue AS monthly_revenue
FROM silver AS s
CROSS JOIN daily AS d
CROSS JOIN monthly AS m
WHERE s.revenue != d.revenue OR s.revenue != m.revenue
