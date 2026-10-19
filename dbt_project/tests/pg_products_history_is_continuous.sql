-- SCD2 rules: one current row per product, and each version ends where the
-- next one starts (no gaps, no overlaps). Any row returned is a failure.
{{ config(tags=['pg_silver']) }}

WITH checked AS (
  SELECT
    product_id,
    valid_from,
    valid_to,
    LEAD(valid_from) OVER (PARTITION BY product_id ORDER BY valid_from) AS next_from,
    COUNTIF(is_current) OVER (PARTITION BY product_id) AS n_current
  FROM {{ ref('pg_dim_products_history') }}
)

SELECT *
FROM checked
WHERE
  n_current != 1
  OR valid_from >= valid_to
  OR (next_from IS NOT NULL AND next_from != valid_to)
