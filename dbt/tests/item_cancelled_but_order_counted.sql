-- Revenue adds up the items of an order that counts. If an ITEM is Cancelled but its ORDER is not,
-- that item is inside revenue. A warning, not a failure: look at how many rows there are, then
-- decide with Finance whether revenue must look at the item status too.
{{ config(tags=['silver'], severity='warn') }}

SELECT
  i.id,
  i.order_id,
  i.status AS item_status,
  o.status AS order_status
FROM {{ ref('fact_order_items') }} AS i
INNER JOIN {{ ref('fact_orders') }} AS o USING (order_id)
WHERE
  i.status = 'Cancelled'
  AND o.status != 'Cancelled'
