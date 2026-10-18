-- Warns when today's revenue of a published month differs from what was
-- published (late or changed rows); the published number stays as it was.
{{ config(tags=['pg_gold'], severity='warn') }}

WITH today AS (
  SELECT
    DATE_TRUNC(order_date, MONTH) AS month,
    SUM(amount) AS revenue_now
  FROM {{ ref('pg_fact_order_items') }}
  WHERE {{ revenue_order_filter('status') }}
  GROUP BY month
)

SELECT
  p.month,
  p.revenue AS revenue_published,
  t.revenue_now
FROM {{ ref('pg_published_monthly_revenue') }} AS p
INNER JOIN today AS t
  ON p.month = t.month
WHERE ABS(p.revenue - t.revenue_now) > 0.01
