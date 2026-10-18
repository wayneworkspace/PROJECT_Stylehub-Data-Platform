-- One row per product; listed columns keep new Bronze columns out.

SELECT
  id,
  name,
  category,
  brand,
  department,
  sku,
  cost,
  retail_price
FROM {{ ref('stg_pg__products') }}
