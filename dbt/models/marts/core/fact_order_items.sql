-- Grain: one row per order item. One row is one unit sold, so there is no quantity column.
-- Measures: sale_price (additive), cost = the product's current cost.

{{ config(
    partition_by={'field': 'created_at', 'data_type': 'timestamp', 'granularity': 'day'},
    cluster_by=['order_id', 'product_id']
) }}

SELECT *
FROM {{ ref('int_order_items_joined_to_products') }}
