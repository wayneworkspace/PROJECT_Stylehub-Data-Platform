-- amount must equal sale_price times quantity; returned rows fail.
{{ config(tags=['pg_silver']) }}

SELECT
  id,
  sale_price,
  quantity,
  amount
FROM {{ ref('pg_fact_order_items') }}
WHERE amount != sale_price * quantity
