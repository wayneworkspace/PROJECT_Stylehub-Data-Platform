{# Revenue rows of the Postgres branch: the revenue status rule plus no rows #}
{# deleted in Postgres. is_deleted is read from the same table as the status. #}
{% macro pg_revenue_filter(status_column) %}
  {%- set prefix = status_column.rsplit('.', 1)[0] ~ '.' if '.' in status_column else '' -%}
  {{ revenue_order_filter(status_column) }} AND NOT {{ prefix }}is_deleted
{%- endmacro %}
