-- Every funnel stage must have events. If the event_type names are wrong the counts are all 0,
-- the rates are NULL, and no range test notices. Any row returned here is a failure.
{{ config(tags=['gold']) }}

WITH totals AS (
  SELECT
    SUM(n_view_sessions) AS n_view_sessions,
    SUM(n_cart_sessions) AS n_cart_sessions,
    SUM(n_purchase_sessions) AS n_purchase_sessions
  FROM {{ ref('funnel_by_category') }}
)

SELECT *
FROM totals
WHERE
  COALESCE(n_view_sessions, 0) = 0
  OR COALESCE(n_cart_sessions, 0) = 0
  OR COALESCE(n_purchase_sessions, 0) = 0
