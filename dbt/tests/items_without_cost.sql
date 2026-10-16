-- Order items whose product has no cost (the product is missing from the product list).
-- Their revenue counts, but their profit is 0. A warning only: look at the list, do not stop.
{{ config(tags=['silver'], severity='warn') }}

SELECT
  id,
  product_id
FROM {{ ref('fact_order_items') }}
WHERE cost IS NULL
