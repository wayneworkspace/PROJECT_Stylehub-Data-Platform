-- The source computes amount as sale_price * quantity, so the mismatched row count must be 0 (session 3).

WITH mismatched AS (
  SELECT COUNT(*) AS n_mismatched
  FROM `${project}.${silver}.fact_order_items`
  WHERE amount != sale_price * quantity
)
SELECT n_mismatched
FROM mismatched
WHERE n_mismatched > 0;
