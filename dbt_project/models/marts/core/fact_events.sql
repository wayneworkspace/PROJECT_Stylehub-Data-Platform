-- One row per event (~108M). A view: the rows already sit once in the
-- partitioned Bronze table, so a 13.5 GB copy here would only cost storage.
-- Tag events keeps it out of daily runs, so its tests do not scan 108M rows a day;
-- after a new events load: dbt build --select tag:events

{{ config(tags=['events'], materialized='view') }}

SELECT
  event_id,
  user_id,
  product_id,
  event_type,
  category_code,
  brand,
  price,
  user_session,
  event_time,
  DATE(event_time) AS event_date
FROM {{ ref('stg_stylehub__events') }}
