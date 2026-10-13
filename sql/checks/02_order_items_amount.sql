-- amount do nguồn tự tính từ sale_price * quantity, số dòng lệch phải bằng 0 (Buổi 3).

WITH mismatched AS (
  SELECT COUNT(*) AS n_mismatched
  FROM `${project}.${silver}.fact_order_items`
  WHERE amount != sale_price * quantity
)
SELECT n_mismatched
FROM mismatched
WHERE n_mismatched > 0;
