{#
  THE revenue rule, in one place: which orders count as revenue.
  The statuses that do NOT count are the dbt variable revenue_excluded_statuses (dbt_project.yml).
  When Finance changes the rule (for example Returned no longer counts), change that variable.
  Used only in Gold (models and the test that checks Gold). Silver keeps every status.
#}
{% macro revenue_order_filter(status_column) %}
  {{- status_column }} NOT IN (
  {%- for status in var('revenue_excluded_statuses', ['Cancelled']) -%}
    '{{ status }}'{% if not loop.last %}, {% endif %}
  {%- endfor -%}
  )
{%- endmacro %}
