-- Small, fixed sample data for local runs and CI. This is NOT the course dataset.
-- Column names match what sql/silver/ expects for orders and order_items.
--
-- What the data contains (so tests can count on it):
--   orders 1..30     created every 2 hours, starting 2026-09-30 02:00
--   order 100        created 2026-09-29, updated 2026-10-01 08:00 (a late update)
--   order 101        created and updated 2026-09-28 (too old for any 2026-10-01 window)
--   order_items 1..60  two items per order 1..30, updated 5 minutes after the order

CREATE TABLE orders (
    id            BIGINT PRIMARY KEY,
    user_id       BIGINT NOT NULL,
    status        TEXT NOT NULL,
    total_amount  NUMERIC(12, 2) NOT NULL,
    created_at    TIMESTAMP NOT NULL,
    updated_at    TIMESTAMP NOT NULL
);

CREATE TABLE order_items (
    id          BIGINT PRIMARY KEY,
    order_id    BIGINT NOT NULL,
    product_id  BIGINT NOT NULL,
    sale_price  NUMERIC(12, 2) NOT NULL,
    quantity    INTEGER NOT NULL,
    amount      NUMERIC(12, 2) NOT NULL,
    created_at  TIMESTAMP NOT NULL,
    updated_at  TIMESTAMP NOT NULL
);

INSERT INTO orders (id, user_id, status, total_amount, created_at, updated_at)
SELECT
    g,
    1 + g % 20,
    (ARRAY['Processing', 'Shipped', 'Complete', 'Cancelled', 'Returned'])[1 + g % 5],
    10 + g % 90,
    TIMESTAMP '2026-09-30 00:00' + g * INTERVAL '2 hours',
    TIMESTAMP '2026-09-30 00:00' + g * INTERVAL '2 hours'
FROM generate_series(1, 30) AS g;

INSERT INTO orders (id, user_id, status, total_amount, created_at, updated_at) VALUES
    (100, 5, 'Shipped', 42.00, '2026-09-29 10:00', '2026-10-01 08:00'),
    (101, 6, 'Complete', 17.50, '2026-09-28 09:00', '2026-09-28 09:00');

INSERT INTO order_items (id, order_id, product_id, sale_price, quantity, amount, created_at, updated_at)
SELECT
    g,
    (g + 1) / 2,
    1 + g % 12,
    5 + g % 10,
    1 + g % 3,
    (5 + g % 10) * (1 + g % 3),
    TIMESTAMP '2026-09-30 00:00' + ((g + 1) / 2) * INTERVAL '2 hours' + INTERVAL '5 minutes',
    TIMESTAMP '2026-09-30 00:00' + ((g + 1) / 2) * INTERVAL '2 hours' + INTERVAL '5 minutes'
FROM generate_series(1, 60) AS g;
