-- One row per product; listed columns keep new Bronze columns out.
-- Products deleted in Postgres stay (is_deleted) so old sales still join.

SELECT
  id,
  name,
  category,
  brand,
  department,
  sku,
  cost,
  retail_price,
  is_deleted,
  deleted_at
FROM {{ ref('stg_pg__products') }}
