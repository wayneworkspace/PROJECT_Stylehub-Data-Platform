-- Grain: one row per product.

SELECT *
FROM {{ ref('stg_stylehub__products') }}
