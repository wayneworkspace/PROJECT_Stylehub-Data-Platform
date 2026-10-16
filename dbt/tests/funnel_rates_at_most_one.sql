-- A funnel rate above 1 means more sessions reached a later stage than the stage before it.
-- funnel_by_category counts a stage only for sessions that reached the stage before, so this can
-- never happen unless the model is wrong. Any row returned here is a failure.
{{ config(tags=['gold']) }}

SELECT
  category,
  view_to_cart_rate,
  cart_to_purchase_rate
FROM {{ ref('funnel_by_category') }}
WHERE
  view_to_cart_rate > 1
  OR cart_to_purchase_rate > 1
