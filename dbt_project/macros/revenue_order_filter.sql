{# The one revenue rule: exclude statuses in revenue_excluded_statuses. Gold only. #}
{% macro revenue_order_filter(status_column) %}
  {{- status_column }} NOT IN (
  {%- for status in var('revenue_excluded_statuses', ['Cancelled']) -%}
    '{{ status }}'{% if not loop.last %}, {% endif %}
  {%- endfor -%}
  )
{%- endmacro %}
