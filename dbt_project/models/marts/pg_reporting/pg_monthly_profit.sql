-- Revenue and profit per month, at the cost on the sale day (SCD2 join)
-- and, for comparison, at today's cost.

SELECT
  DATE_TRUNC(order_date, MONTH) AS month,
  SUM(amount) AS revenue,
  SUM(total_cost_at_sale) AS cost_at_sale,
  SUM(amount) - SUM(total_cost_at_sale) AS profit_at_sale_cost,
  SUM(amount) - SUM(total_cost) AS profit_at_current_cost,
  COUNTIF(total_cost_at_sale IS NULL) AS n_items_without_cost
FROM {{ ref('pg_fact_order_items') }}
WHERE {{ revenue_order_filter('status') }} AND NOT is_deleted
GROUP BY month
