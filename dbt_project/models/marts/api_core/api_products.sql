-- One row per API product, newest snapshot, with its margin.

SELECT
  id AS product_id,
  name,
  category,
  brand,
  department,
  sku,
  cost,
  retail_price,
  retail_price - cost AS margin,
  created_at,
  updated_at
FROM {{ ref('stg_api__products') }}
