-- Warns when today's revenue of a published month differs from its latest
-- published version (late or changed rows); the published number stays as it was.
-- To publish the new number, restate the month (see pg_published_monthly_revenue).
{{ config(tags=['pg_gold'], severity='warn') }}

WITH today AS (
  SELECT
    DATE_TRUNC(order_date, MONTH) AS month,
    SUM(amount) AS revenue_now
  FROM {{ ref('pg_fact_order_items') }}
  WHERE {{ pg_revenue_filter('status') }}
  GROUP BY month
),

published AS (
  SELECT
    month,
    revenue,
    COALESCE(version_number, 1) AS version_number
  FROM {{ ref('pg_published_monthly_revenue') }}
  QUALIFY ROW_NUMBER() OVER (PARTITION BY month ORDER BY COALESCE(version_number, 1) DESC) = 1
)

SELECT
  p.month,
  p.version_number,
  p.revenue AS revenue_published,
  t.revenue_now
FROM published AS p
INNER JOIN today AS t
  ON p.month = t.month
WHERE ABS(p.revenue - t.revenue_now) > 0.01
