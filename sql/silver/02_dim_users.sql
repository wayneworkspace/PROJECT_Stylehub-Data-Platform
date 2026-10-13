-- Grain: một dòng là một khách hàng. Gom mọi thông tin của khách (Buổi 5, Bài tập 2).
-- Kiểm tra tên cột với schema thật trước khi chạy.

CREATE OR REPLACE TABLE `${project}.${silver}.dim_users` AS
WITH latest AS (
  SELECT *
  FROM `${project}.${bronze}.users`
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY _ingested_at DESC) = 1
)
SELECT
  id,
  email,
  country,
  state,
  city,
  street_address,
  latitude,
  longitude,
  traffic_source
FROM latest;
