-- Top 5 customers by revenue in each month; ties share a rank.

WITH customer_revenue AS (
  SELECT
    DATE_TRUNC(order_date, MONTH) AS month,
    user_id,
    SUM(amount) AS revenue
  FROM {{ ref('pg_fact_order_items') }}
  WHERE {{ revenue_order_filter('status') }}
  GROUP BY month, user_id
),

ranked AS (
  SELECT
    month,
    user_id,
    revenue,
    RANK() OVER (PARTITION BY month ORDER BY revenue DESC) AS revenue_rank
  FROM customer_revenue
)

SELECT
  month,
  revenue_rank,
  user_id,
  revenue
FROM ranked
WHERE revenue_rank <= 5
