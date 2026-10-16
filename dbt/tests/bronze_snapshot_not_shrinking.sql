-- Silver is rebuilt from the NEWEST Bronze snapshot only. A snapshot that is much smaller than the
-- one before it (a cut-off source, a half-empty export) would silently shrink Silver and Gold,
-- and every other test would still pass. The newest snapshot must hold at least
-- bronze_min_snapshot_ratio (default 0.9) of the rows of the one before it.
-- This test reads only Bronze, so dbt build runs it BEFORE the models that read Bronze.
-- Any row returned here is a failure.
{{ config(tags=['silver']) }}

-- _PARTITIONDATE is a BigQuery name that must keep its capitals in this repo (see the macro).
-- noqa: disable=CP02

{% set ratio = var('bronze_min_snapshot_ratio', 0.9) %}
{% set tables = ['orders', 'order_items', 'products', 'users'] %}

WITH counts AS (
  {%- for table_name in tables %}
    SELECT
      '{{ table_name }}' AS table_name,
      _PARTITIONDATE AS snapshot_day,
      COUNT(*) AS n_rows
    FROM {{ source('stylehub', table_name) }}
    WHERE _PARTITIONDATE IS NOT NULL
    GROUP BY snapshot_day
    {% if not loop.last %}UNION ALL{% endif %}
  {%- endfor %}
),

ranked AS (
  SELECT
    table_name,
    snapshot_day,
    n_rows,
    ROW_NUMBER() OVER (PARTITION BY table_name ORDER BY snapshot_day DESC) AS recency
  FROM counts
),

newest AS (
  SELECT *
  FROM ranked
  WHERE recency = 1
),

previous AS (
  SELECT *
  FROM ranked
  WHERE recency = 2
)

SELECT
  newest.table_name,
  newest.snapshot_day AS newest_day,
  newest.n_rows AS newest_rows,
  previous.snapshot_day AS previous_day,
  previous.n_rows AS previous_rows
FROM newest
INNER JOIN previous USING (table_name)
WHERE newest.n_rows < previous.n_rows * {{ ratio }}
