-- Order items of the last 90 days for EDA; partition filter keeps cost low.
SELECT
  i.id,
  i.order_id,
  i.user_id,
  i.status,
  i.sale_price,
  i.quantity,
  i.amount,
  i.cost,
  i.total_cost,
  i.order_date,
  p.category,
  u.state,
  u.traffic_source,
  u.age
FROM `${project}.${silver}.pg_fact_order_items` AS i
LEFT JOIN `${project}.${silver}.pg_dim_products` AS p
  ON i.product_id = p.id
LEFT JOIN `${project}.${silver}.pg_dim_users` AS u
  ON i.user_id = u.id
WHERE i.order_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
