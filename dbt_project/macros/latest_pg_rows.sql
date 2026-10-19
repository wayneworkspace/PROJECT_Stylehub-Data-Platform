{# Newest version of each id across all incremental Bronze partitions, #}
{# without ids deleted in Postgres (pg_deleted_ids, written by pg_reconcile). #}
{% macro latest_pg_rows(table_name) %}
  SELECT *
  FROM {{ source('stylehub_pg', table_name) }}
  WHERE id NOT IN (
    SELECT d.id
    FROM {{ source('stylehub_pg', 'pg_deleted_ids') }} AS d
    WHERE d.table_name = '{{ table_name | replace("pg_", "", 1) }}'
  )
  QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY updated_at DESC, _ingested_at DESC) = 1
{% endmacro %}
