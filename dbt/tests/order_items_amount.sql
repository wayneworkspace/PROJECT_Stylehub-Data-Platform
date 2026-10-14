-- num_of_item on the order must equal the number of item rows of that order.
{{ config(tags=['silver']) }}

WITH counted AS (
  SELECT order_id, COUNT(*) AS n_items
  FROM {{ ref('fact_order_items') }}
  GROUP BY order_id
)
SELECT
  o.order_id,
  o.num_of_item,
  c.n_items
FROM {{ ref('fact_orders') }} AS o
LEFT JOIN counted AS c USING (order_id)
WHERE o.num_of_item != COALESCE(c.n_items, 0)
