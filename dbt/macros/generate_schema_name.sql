{#
  In prod, the custom schema is used as it is (stylehub_silver, stylehub_gold), so these names stay
  the same as the ones the SQL-file pipeline uses.

  In any other target (dev), the dataset gets the target's dataset as a prefix, for example
  dbt_quang_stylehub_silver. A dbt run by hand then never touches the real datasets.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
  {%- if custom_schema_name is none -%}
    {{ target.schema }}
  {%- elif target.name == 'prod' -%}
    {{ custom_schema_name | trim }}
  {%- else -%}
    {{ target.schema }}_{{ custom_schema_name | trim }}
  {%- endif -%}
{%- endmacro %}
