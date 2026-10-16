-- Prices and costs can never be negative. Any row returned here is a failure.
{{ config(tags=['silver']) }}

SELECT
  id,
  sale_price,
  cost
FROM {{ ref('fact_order_items') }}
WHERE
  sale_price < 0
  OR cost < 0
