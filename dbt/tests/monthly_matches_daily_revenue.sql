-- The two Gold revenue tables must tell the same story: total revenue by month and category
-- must equal total revenue by day. A join that drops items would make them differ.
{{ config(tags=['gold']) }}

WITH monthly AS (
  SELECT SUM(revenue) AS total
  FROM {{ ref('monthly_revenue_by_category') }}
),

daily AS (
  SELECT SUM(revenue) AS total
  FROM {{ ref('daily_revenue') }}
)

SELECT
  monthly.total AS monthly_total,
  daily.total AS daily_total
FROM monthly
CROSS JOIN daily
WHERE monthly.total IS DISTINCT FROM daily.total
