{# fact_events test window: newest event_date minus lookback days. #}
{% macro events_test_window() %}
  {%- if not execute -%}
    DATE '1970-01-01'
  {%- else -%}
    {%- set sql = 'SELECT MAX(event_date) AS d FROM ' ~ ref('fact_events') -%}
    {%- set last_day = run_query(sql).columns[0][0] -%}
    {%- if last_day is none -%}
      DATE '1970-01-01'
    {%- else -%}
      DATE_SUB(DATE '{{ last_day }}', INTERVAL {{ var('events_lookback_days', 3) }} DAY)
    {%- endif -%}
  {%- endif -%}
{%- endmacro %}
