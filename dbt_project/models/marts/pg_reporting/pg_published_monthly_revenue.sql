-- Monthly revenue as published: each closed month is written once as version 1
-- and never changes, so a report keeps the number its readers saw. Late rows for
-- a published month show up in the drift test. To publish a corrected number,
-- name the month; it is added as a new 'restated' version and the old one stays:
--   dbt build --select pg_published_monthly_revenue
--     --vars '{restate_months: ["2026-09-01"], restate_note: "September returns"}'

-- full_refresh=false: --full-refresh must never replace what was published.
{{ config(materialized='incremental', on_schema_change='append_new_columns', full_refresh=false) }}

{%- set restate_months = var('restate_months', []) %}

WITH monthly AS (
  SELECT
    DATE_TRUNC(order_date, MONTH) AS month,
    SUM(amount) AS revenue,
    COUNT(DISTINCT order_id) AS orders
  FROM {{ ref('pg_fact_order_items') }}
  WHERE
    {{ pg_revenue_filter('status') }}
    AND order_date < DATE_TRUNC(CURRENT_DATE(), MONTH)
  GROUP BY month
),

{% if is_incremental() %}
  latest AS (
    SELECT
      month,
      revenue,
      orders,
      {{ published_version() }} AS version_number
    FROM {{ this }}
    QUALIFY ROW_NUMBER() OVER (PARTITION BY month ORDER BY {{ published_version() }} DESC) = 1
  ),

  to_write AS (
    SELECT
      m.month,
      m.revenue,
      m.orders,
      COALESCE(l.version_number, 0) + 1 AS version_number,
      l.month IS NOT NULL AS is_restated
    FROM monthly AS m
    LEFT JOIN latest AS l
      ON m.month = l.month
    WHERE
      l.month IS NULL
      {% if restate_months %}
        OR (
          m.month IN (
            {%- for month in restate_months %}
              DATE '{{ month }}'{{ "," if not loop.last }}
            {%- endfor %}
          )
          AND (ABS(m.revenue - l.revenue) > 0.01 OR m.orders != l.orders)
        )
      {% endif %}
  )
{% else %}
  to_write AS (
    SELECT
      month,
      revenue,
      orders,
      1 AS version_number,
      FALSE AS is_restated
    FROM monthly
  )
{% endif %}

SELECT
  month,
  revenue,
  orders,
  CURRENT_TIMESTAMP() AS published_at,
  version_number,
  IF(is_restated, 'restated', 'published') AS status,
  IF(is_restated, '{{ var("restate_note", "Restated") | replace("'", "") }}', NULL) AS note
FROM to_write
