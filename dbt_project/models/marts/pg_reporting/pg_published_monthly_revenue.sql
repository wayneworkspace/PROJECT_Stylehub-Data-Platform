-- Monthly revenue as published: each closed month is written once and never
-- changes, so a report keeps the number its readers saw. Late rows for a
-- published month show up in the drift test, not here.

{{ config(materialized='incremental', on_schema_change='fail') }}

WITH monthly AS (
  SELECT
    DATE_TRUNC(order_date, MONTH) AS month,
    SUM(amount) AS revenue,
    COUNT(DISTINCT order_id) AS orders
  FROM {{ ref('pg_fact_order_items') }}
  WHERE
    {{ revenue_order_filter('status') }}
    AND order_date < DATE_TRUNC(CURRENT_DATE(), MONTH)
  GROUP BY month
)

SELECT
  month,
  revenue,
  orders,
  CURRENT_TIMESTAMP() AS published_at
FROM monthly
{% if is_incremental() %}
  WHERE month > (SELECT MAX(t.month) FROM {{ this }} AS t)
{% endif %}
