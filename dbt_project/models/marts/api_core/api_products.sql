-- One row per API product, with the price after its discount.

SELECT
  id AS product_id,
  title,
  category,
  brand,
  price,
  discount_percentage,
  ROUND(price * (1 - discount_percentage / 100), 2) AS price_after_discount,
  rating,
  stock,
  availability_status,
  updated_at
FROM {{ ref('stg_api__products') }}
