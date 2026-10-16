-- Gold sanity: revenue is not negative (or NULL) and no rate is below 0.
-- The upper bound of the funnel rates is a warning in funnel_rates_at_most_one.
-- Tagged gold because it reads Gold tables.
{{ config(tags=['gold']) }}

WITH bad_revenue AS (
  SELECT 'daily_revenue' AS table_name, CAST(order_date AS STRING) AS row_key
  FROM {{ ref('daily_revenue') }}
  WHERE revenue IS NULL OR revenue < 0  -- a NULL must fail too: NULL < 0 is not true
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
