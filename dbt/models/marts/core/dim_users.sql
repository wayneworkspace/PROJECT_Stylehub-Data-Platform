-- Grain: one row per customer. Gathers everything about a customer (session 5, exercise 2).

SELECT *
FROM {{ ref('stg_stylehub__users') }}
