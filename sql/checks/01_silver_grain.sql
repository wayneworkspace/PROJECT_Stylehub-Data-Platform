-- Grain: số dòng phải bằng số id khác nhau. Trả về dòng nếu bảng nào vi phạm.

WITH grains AS (
  SELECT 'dim_products' AS table_name, COUNT(*) AS n_rows, COUNT(DISTINCT id) AS n_ids
  FROM `${project}.${silver}.dim_products`
  UNION ALL
  SELECT 'dim_users', COUNT(*), COUNT(DISTINCT id)
  FROM `${project}.${silver}.dim_users`
  UNION ALL
  SELECT 'fact_orders', COUNT(*), COUNT(DISTINCT id)
  FROM `${project}.${silver}.fact_orders`
  UNION ALL
  SELECT 'fact_order_items', COUNT(*), COUNT(DISTINCT id)
  FROM `${project}.${silver}.fact_order_items`
  UNION ALL
  SELECT 'fact_shipments', COUNT(*), COUNT(DISTINCT id)
  FROM `${project}.${silver}.fact_shipments`
)
SELECT *
FROM grains
WHERE n_rows != n_ids;
