{#
  The newest snapshot of a Bronze table, and nothing older.

  Bronze keeps one full copy (snapshot) of each table per day, in its own partition. Every
  snapshot is a COMPLETE copy of the source, so the newest one is the current truth.

  The newest day is looked up first, then written into the SQL as a fixed date. A fixed date lets
  BigQuery read only that one partition (a plain "max date" in the same query would not).

  Fails on purpose when Bronze has no partition at all: an empty Silver would pass every test and
  produce a Gold with zero revenue.
#}
{% macro latest_bronze_snapshot(table_name) %}
  {%- set relation = source('stylehub', table_name) -%}
  {%- if execute -%}
    {%- set sql = 'SELECT MAX(_PARTITIONDATE) AS d FROM ' ~ relation -%}
    {%- set latest_day = run_query(sql).columns[0][0] -%}
    {%- if latest_day is none -%}
      {{ exceptions.raise_compiler_error(
        "Bronze table " ~ relation ~ " has no partition. Run the ingest and bronze steps first."
      ) }}
    {%- endif -%}
  {%- endif -%}
  SELECT *
  FROM {{ relation }}
  {% if execute -%}
    WHERE _PARTITIONDATE = DATE '{{ latest_day }}'
  {%- endif %}
{% endmacro %}
