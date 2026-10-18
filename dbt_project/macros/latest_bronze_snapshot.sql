{# Newest Bronze snapshot; a fixed date reads only one partition. #}
{# Fails when Bronze is empty, so Gold never shows zero revenue. #}
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
