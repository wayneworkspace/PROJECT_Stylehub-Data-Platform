-- Question: from view to cart to purchase, by product category.
-- Rules at Gold: a funnel follows ONE session. A session counts for a stage only if it reached
-- the stage before, in time order: n_cart_sessions = sessions that viewed and THEN added to cart,
-- n_purchase_sessions = sessions that viewed, then carted, then bought. So each rate is at most 1.
-- Stages are the event_type values 'view', 'cart' and 'purchase'. Events without a session id
-- cannot be followed and are left out. Events whose product is unknown stay under 'Unknown'.
-- A session that touched two categories counts once in EACH, so the rows are not additive.
-- If the stage names are wrong the counts are 0: the test funnel_not_empty fails when that happens.
-- It reads all events on each run (a session can cross midnight, so a day-by-day rebuild would
-- be wrong). The events data is static and this is about 6 GB, see docs/design/DECISIONS.md.

WITH events AS (
  SELECT
    product_id,
    event_type,
    user_session,
    event_time
  FROM {{ ref('fact_events') }}
  WHERE
    event_type IN ('view', 'cart', 'purchase')
    AND user_session IS NOT NULL
),

session_stages AS (
  SELECT
    COALESCE(p.category, 'Unknown') AS category,
    e.user_session,
    MIN(IF(e.event_type = 'view', e.event_time, NULL)) AS first_view_at,
    MIN(IF(e.event_type = 'cart', e.event_time, NULL)) AS first_cart_at,
    MIN(IF(e.event_type = 'purchase', e.event_time, NULL)) AS first_purchase_at
  FROM events AS e
  LEFT JOIN {{ ref('dim_products') }} AS p
    ON e.product_id = p.id
  GROUP BY category, e.user_session
),

by_category AS (
  SELECT
    category,
    COUNTIF(first_view_at IS NOT NULL) AS n_view_sessions,
    COUNTIF(first_cart_at >= first_view_at) AS n_cart_sessions,
    COUNTIF(first_purchase_at >= first_cart_at AND first_cart_at >= first_view_at)
      AS n_purchase_sessions
  FROM session_stages
  GROUP BY category
)

SELECT
  *,
  SAFE_DIVIDE(n_cart_sessions, n_view_sessions) AS view_to_cart_rate,
  SAFE_DIVIDE(n_purchase_sessions, n_cart_sessions) AS cart_to_purchase_rate
FROM by_category
