{#
  The start of the window that the tests of fact_events look at: the newest event_date minus the
  same lookback days that the incremental model rebuilds. Older partitions do not change in a daily
  run, so scanning them again every day only costs money. After a --full-refresh run the full table
  test by hand:  dbt test --select fact_events --vars "{events_test_full: true}"
  While dbt only reads the project (parse), there is no table to ask, so a fixed date is returned.
#}
{% macro events_test_window() %}
  {%- if var('events_test_full', false) or not execute -%}
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
