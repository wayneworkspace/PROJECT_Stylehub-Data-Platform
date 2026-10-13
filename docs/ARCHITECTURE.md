# Kiến trúc

## Các tầng

| Tầng | Nơi lưu | Nội dung | Ai ghi |
|---|---|---|---|
| Raw Zone | GCS `raw/stylehub/<bảng>/date=<ngày>/batch_id=<id>/` | File vừa lấy về, append-only, có `_ingested_at`, `_source`, `_batch_id` | `ingestion/` hoặc Airbyte |
| Bronze | BigQuery `stylehub_bronze` | Bản sao nguồn, giữ mọi lần ingest | `pipeline/load_bronze.py` |
| Silver | BigQuery `stylehub_silver` | Đã sạch, tổ chức thành fact và dimension | `sql/silver/` |
| Gold | BigQuery `stylehub_gold` | Bảng nghiệp vụ, chứa rule | `sql/gold/` |

Rule nghiệp vụ đổi thì chạy lại từ tầng gần nhất: sửa Gold, Silver giữ nguyên.

## Star schema (Silver)

| Bảng | Grain | Loại |
|---|---|---|
| fact_order_items | một món hàng | fact |
| fact_orders | một đơn hàng | fact |
| fact_shipments | một lô giao hàng | fact |
| dim_products | một sản phẩm | dimension |
| dim_users | một khách hàng | dimension |

`events` (hành vi, ~108 triệu dòng) nằm ở Bronze dưới dạng `events_partitioned`. Khi cần mô hình hóa sẽ thêm `fact_events` và `dim_date` vào Silver.

## Gold hiện có

| Bảng | Trả lời câu hỏi |
|---|---|
| daily_revenue | Doanh thu và số đơn mỗi ngày (bỏ Cancelled) |
| monthly_revenue_by_category | Doanh thu, lợi nhuận theo category mỗi tháng |
| return_rate_by_state | Tỷ lệ đơn bị trả lại theo bang |
| avg_delivery_days_by_state | Thời gian giao hàng trung bình theo bang |

## Ingestion (Buổi 2 và 4)

- **Python** (`ingestion/`): dùng khi cần kiểm soát từng bước: chọn watermark, lookback, đường dẫn Raw.
- **Airbyte OSS** trên VM GCP (`e2-standard-4`, `asia-southeast1-b`): dùng cho Postgres và API (Connector Builder).

Sync mode Airbyte (theo Buổi 4):

| Bảng | Mode | Lý do |
|---|---|---|
| orders | Incremental, Append (cursor `updated_at`) | Đơn đổi trạng thái là thêm một dòng, giữ mọi phiên bản |
| order_items | Incremental, Append (cursor chọn sau khi kiểm tra data thật) | Xem DECISIONS.md mục 2 |
| products | Full Refresh, Overwrite | Bảng nhỏ, cần snapshot đầy đủ |
| shipments | Cần quyết định, ghi vào DECISIONS.md | |

Vận hành: tắt VM Airbyte sau khi dùng, firewall port 8000 chỉ cho IP của mình.

## Điểm cắm cho mở rộng

Mỗi bước là một CLI độc lập có `--date`, an toàn khi chạy lại. Chi tiết cách thêm dbt, Airflow, Spark ở [EXTENDING.md](EXTENDING.md).
