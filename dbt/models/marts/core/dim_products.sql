-- Grain: one row per product.
-- The columns are listed on purpose: a new column in Bronze must not reach the marts by accident.

SELECT
  id,
  name,
  category,
  brand,
  department,
  sku,
  cost,
  retail_price
FROM {{ ref('stg_stylehub__products') }}
