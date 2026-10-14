{#
  By default dbt names a dataset "<target dataset>_<custom schema>".
  We want the custom schema as it is (stylehub_silver, stylehub_gold),
  so these names stay the same as the ones the SQL-file pipeline uses.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
  {%- if custom_schema_name is none -%}
    {{ target.schema }}
  {%- else -%}
    {{ custom_schema_name | trim }}
  {%- endif -%}
{%- endmacro %}
