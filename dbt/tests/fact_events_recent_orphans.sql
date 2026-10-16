-- Events whose user or product is not in dim_users / dim_products, in the recent window only.
-- A warning: some events have no user or no product on purpose; look at the number of rows.
{{ config(tags=['silver'], severity='warn') }}

WITH recent AS (
  SELECT event_id, user_id, product_id
  FROM {{ ref('fact_events') }}
  WHERE event_date >= {{ events_test_window() }}
)

SELECT
  r.event_id,
  r.user_id,
  r.product_id
FROM recent AS r
LEFT JOIN {{ ref('dim_users') }} AS u
  ON r.user_id = u.id
LEFT JOIN {{ ref('dim_products') }} AS p
  ON r.product_id = p.id
WHERE
  (r.user_id IS NOT NULL AND u.id IS NULL)
  OR (r.product_id IS NOT NULL AND p.id IS NULL)
