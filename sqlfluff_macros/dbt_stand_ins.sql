{# Simple stand-ins for the dbt functions, only for sqlfluff. dbt itself never reads this folder. #}
{% macro ref(name) %}{{ name }}{% endmacro %}
{% macro source(source_name, table_name) %}{{ source_name }}.{{ table_name }}{% endmacro %}
{% macro config() %}{% set _ignored = kwargs %}{% endmacro %}
{% macro is_incremental() %}False{% endmacro %}
{% macro var(name, default=None) %}{{ default }}{% endmacro %}
{% macro latest_bronze_snapshot(table_name) %}SELECT * FROM bronze.{{ table_name }}{% endmacro %}
{% macro revenue_order_filter(status_column) %}{{ status_column }} NOT IN ('Cancelled'){% endmacro %}
{% macro events_test_window() %}DATE '1970-01-01'{% endmacro %}
