-- SCD Type 2 for products: dbt adds dbt_valid_from and dbt_valid_to, and writes a new row
-- each time one of the columns changes. dbt_valid_to is NULL while the version is current.
-- The history starts at the first run of `dbt snapshot` (or `dbt build`, which includes it).
{% snapshot products_history %}

{{ config(unique_key='id', strategy='check', check_cols='all') }}

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
