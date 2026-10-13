# Lộ trình theo giáo trình

## Buổi 1: Data Platform
- [ ] Project GCP, bucket GCS, ba dataset BigQuery, service account
- [ ] Upload CSV lên GCS, load 5 bảng vào BigQuery, so bytes processed với size file gốc
- [ ] `events_partitioned` (`sql/bronze/01_events_partitioned.sql`)
- [ ] Đo 3 query, ghi vào `docs/DECISIONS.md` mục 1

## Buổi 2: Data Ingestion
- [ ] Kiểm tra `updated_at` của order_items rồi chọn watermark (`docs/DECISIONS.md` mục 2)
- [ ] `make ingest` cho orders, order_items; backfill 7 ngày; chạy lại không đổi số id
- [ ] Ingestion `products` từ API vào `raw/stylehub/products_api/` (ghi đè theo ngày)

## Buổi 3: Transform và phân tầng
- [ ] `make bronze` nạp orders, order_items, products
- [ ] Silver `fact_orders`, `fact_order_items`, `dim_products`
- [ ] Gold `daily_revenue`, `make check` đạt

## Buổi 4: Ingestion tool
- [ ] VM Airbyte trên GCP, firewall theo IP của mình
- [ ] Connection Postgres → BigQuery cho orders, order_items, products, shipments
- [ ] Connector Builder cho API StyleHub
- [ ] Ghi sync mode từng bảng vào `docs/DECISIONS.md` mục 3

## Buổi 5: Data modeling
- [ ] Điền bảng thiết kế (câu hỏi, sự kiện, grain, số đo, chiều) cho 5 câu hỏi
- [ ] Silver đủ 5 bảng, `make check` đạt grain
- [ ] Gold: doanh thu theo category, tỷ lệ trả hàng, thời gian giao hàng

## Sau giáo trình
Xem [EXTENDING.md](EXTENDING.md): dbt, Airflow, Spark. Thêm dữ liệu tăng dần mỗi ngày (1.000 đến 4.000 dòng) để pipeline chạy thật.
