{# Newest version of each id across all incremental Bronze partitions. #}
{# Ids deleted in Postgres stay, flagged is_deleted (pg_deleted_ids, written by pg_reconcile), #}
{# so old facts still join to them. #}
{% macro latest_pg_rows(table_name) %}
  SELECT
    b.*,
    d.id IS NOT NULL AS is_deleted,
    d.detected_at AS deleted_at
  FROM {{ source('stylehub_pg', table_name) }} AS b
  LEFT JOIN {{ source('stylehub_pg', 'pg_deleted_ids') }} AS d
    ON
      b.id = d.id
      AND d.table_name = '{{ table_name | replace("pg_", "", 1) }}'
  QUALIFY ROW_NUMBER() OVER (PARTITION BY b.id ORDER BY b.updated_at DESC, b._ingested_at DESC) = 1
{% endmacro %}
