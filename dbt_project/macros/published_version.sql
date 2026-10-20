{# Version of a row already in pg_published_monthly_revenue. Rows written before #}
{# versions existed have none and count as 1; the first run after the change #}
{# reads a table without the column. #}
-- shortcut: needed only until the first production run after the merge; then delete
-- this macro and use COALESCE(version_number, 1) in pg_published_monthly_revenue.
{% macro published_version() %}
  {%- set columns = adapter.get_columns_in_relation(this) | map(attribute='name') | list -%}
  {{- 'COALESCE(version_number, 1)' if 'version_number' in columns else '1' -}}
{% endmacro %}
