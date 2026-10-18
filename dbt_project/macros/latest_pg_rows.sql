{# Newest version of each id across all incremental Bronze partitions. #}
{% macro latest_pg_rows(table_name) %}
  SELECT *
  FROM {{ source('stylehub_pg', table_name) }}
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_at DESC, _ingested_at DESC) = 1
{% endmacro %}
