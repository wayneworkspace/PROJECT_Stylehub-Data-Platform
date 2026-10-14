-- Gold sanity: revenue is not negative and every rate is between 0 and 1.
-- Tagged gold because it reads Gold tables.
{{ config(tags=['gold']) }}

WITH bad_revenue AS (
  SELECT 'daily_revenue' AS table_name, CAST(order_date AS STRING) AS row_key
  FROM {{ ref('daily_revenue') }}
  WHERE revenue < 0
),
bad_returns AS (
  SELECT 'return_rate_by_state' AS table_name, state AS row_key
  FROM {{ ref('return_rate_by_state') }}
  WHERE return_rate < 0 OR return_rate > 1
),
bad_funnel AS (
  SELECT 'funnel_by_category' AS table_name, category AS row_key
  FROM {{ ref('funnel_by_category') }}
  WHERE view_to_cart_rate < 0 OR cart_to_purchase_rate < 0
)
SELECT * FROM bad_revenue
UNION ALL
SELECT * FROM bad_returns
UNION ALL
SELECT * FROM bad_funnel
