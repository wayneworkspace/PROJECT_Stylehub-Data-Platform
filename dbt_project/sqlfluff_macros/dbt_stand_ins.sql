{# Stand-ins for dbt functions, read only by sqlfluff. #}
{% macro ref(name) %}{{ name }}{% endmacro %}
{% macro source(source_name, table_name) %}{{ source_name }}.{{ table_name }}{% endmacro %}
{% macro config() %}{% set _ignored = kwargs %}{% endmacro %}
{% macro is_incremental() %}False{% endmacro %}
{% macro var(name, default=None) %}{{ default }}{% endmacro %}
{% macro latest_bronze_snapshot(table_name, source_name='stylehub') %}SELECT * FROM bronze.{{ table_name }}{% endmacro %}
{% macro revenue_order_filter(status_column) %}{{ status_column }} NOT IN ('Cancelled'){% endmacro %}
{% macro events_test_window() %}DATE '1970-01-01'{% endmacro %}
{% macro latest_pg_rows(table_name) %}SELECT * FROM bronze.{{ table_name }}{% endmacro %}
{% macro published_version() %}COALESCE(version_number, 1){% endmacro %}
{% macro pg_revenue_filter(status_column) %}{{ status_column }} NOT IN ('Cancelled') AND NOT is_deleted{% endmacro %}
