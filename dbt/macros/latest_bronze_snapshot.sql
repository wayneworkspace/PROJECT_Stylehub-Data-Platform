{#
  The newest snapshot of a Bronze table, and nothing older.

  Bronze keeps one full copy (snapshot) of each table per day, in its own partition. Every
  snapshot is a COMPLETE copy of the source, so the newest one is the current truth. Reading
  all of them and picking the newest row of each id (as staging did before) makes every run
  scan more data each day, and it can never notice a row that the source deleted.

  The newest day is looked up first, then written into the SQL as a fixed date. A fixed date lets
  BigQuery read only that one partition. If it only said "the max date" in the same query, BigQuery
  could not choose the partition before it runs the query.

  The day normally comes from the variable bronze_snapshot_dates, which the pipeline reads ONCE
  per run (stylehub.transform.run_dbt) and also records in pipeline_runs.detail. So all models and
  tests of one run read the same snapshot, and a run can be repeated exactly:
    dbt build --vars '{bronze_snapshot_dates: {orders: "2026-10-16", ...}}'
  Without the variable (dbt run by hand) the newest day is looked up at compile time, as before.
  Staging views keep showing that day until the next dbt run.

  Fails on purpose when Bronze has no partition at all (for example all of them expired): an empty
  Silver would pass every test and produce a Gold with zero revenue.
#}
{% macro latest_bronze_snapshot(table_name) %}
  {%- set relation = source('stylehub', table_name) -%}
  {%- set pinned = var('bronze_snapshot_dates', {}).get(table_name) -%}
  {%- set latest_day = pinned -%}
  {%- if execute and pinned is none -%}
    {%- set sql = 'SELECT MAX(_PARTITIONDATE) AS d FROM ' ~ relation -%}
    {%- set latest_day = run_query(sql).columns[0][0] -%}
  {%- endif -%}
  {%- if execute -%}
    {%- if latest_day is none -%}
      {%- set message = "Bronze table " ~ relation ~ " has no partition. "
        ~ "Run the ingest and bronze steps first." -%}
      {{ exceptions.raise_compiler_error(message) }}
    {%- endif -%}
  {%- endif -%}
  SELECT *
  FROM {{ relation }}
  {% if latest_day is not none -%}
    WHERE _PARTITIONDATE = DATE '{{ latest_day }}'
  {%- endif %}
{% endmacro %}
