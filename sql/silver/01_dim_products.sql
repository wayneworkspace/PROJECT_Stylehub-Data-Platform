-- Grain: một dòng là một sản phẩm.
-- Bronze giữ mọi snapshot theo ngày; Silver lấy snapshot nạp sau cùng của mỗi id.
-- Kiểm tra tên cột với schema thật trước khi chạy.

CREATE OR REPLACE TABLE `${project}.${silver}.dim_products` AS
WITH latest AS (
  SELECT *
  FROM `${project}.${bronze}.products`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY _ingested_at DESC) = 1
)
SELECT
  id,
  name,
  category,
  brand,
  CAST(cost AS NUMERIC) AS cost,
  CAST(retail_price AS NUMERIC) AS retail_price
FROM latest;
