-- Revenue, orders and customers per region and country, with country names
-- cleaned by the country_regions seed (Brasil and Brazil count once).

WITH items AS (
  SELECT
    i.order_id,
    i.user_id,
    i.amount,
    u.country
  FROM {{ ref('pg_fact_order_items') }} AS i
  LEFT JOIN {{ ref('pg_dim_users') }} AS u
    ON i.user_id = u.id
  WHERE {{ revenue_order_filter('i.status') }}
)

SELECT
  COALESCE(r.region, 'Unknown') AS region,
  COALESCE(r.country_name, items.country, 'Unknown') AS country,
  SUM(items.amount) AS revenue,
  COUNT(DISTINCT items.order_id) AS orders,
  COUNT(DISTINCT items.user_id) AS customers
FROM items
LEFT JOIN {{ ref('country_regions') }} AS r
  ON items.country = r.country
GROUP BY region, country
