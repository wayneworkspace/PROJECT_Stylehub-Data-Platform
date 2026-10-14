-- Question: from view to cart to purchase, by product category.
-- Rules at Gold: stages are the event_type values 'view', 'cart' and 'purchase'.
-- Check the real event_type values first (list them with GROUP BY), or the counts stay 0.

WITH events AS (
  SELECT product_id, event_type
  FROM {{ ref('fact_events') }}
),
by_category AS (
  SELECT
    p.category,
    COUNTIF(e.event_type = 'view') AS n_views,
    COUNTIF(e.event_type = 'cart') AS n_carts,
    COUNTIF(e.event_type = 'purchase') AS n_purchases
  FROM events AS e
  INNER JOIN {{ ref('dim_products') }} AS p
    ON e.product_id = p.id
  GROUP BY p.category
)
SELECT
  *,
  SAFE_DIVIDE(n_carts, n_views) AS view_to_cart_rate,
  SAFE_DIVIDE(n_purchases, n_carts) AS cart_to_purchase_rate
FROM by_category
