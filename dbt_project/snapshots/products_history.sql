-- SCD Type 2 for products; dbt_valid_to is NULL while current.
{% snapshot products_history %}

{{ config(unique_key='id', strategy='check', check_cols='all', tags=['silver']) }}

SELECT
  id,
  name,
  category,
  brand,
  department,
  sku,
  cost,
  retail_price
FROM {{ ref('stg_stylehub__products') }}

{% endsnapshot %}
