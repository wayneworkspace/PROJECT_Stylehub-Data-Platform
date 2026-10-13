# StyleHub Data Platform

Data platform trên GCP cho dataset StyleHub (users, products, orders, order_items, shipments, events ~108 triệu dòng), xây đúng theo giáo trình 5 buổi. Cấu trúc để sau này thêm dbt, Airflow, Spark mà không phải viết lại.

```
Postgres + API ─► Raw Zone (GCS) ─► Bronze ─► Silver (fact/dim) ─► Gold
   (Python / Airbyte)            (BigQuery, 3 dataset)
```

## Repo theo từng buổi

| Buổi | Nội dung | Nằm ở |
|---|---|---|
| 1 | GCS + BigQuery, partition/cluster, đo bytes processed | `sql/bronze/01_events_partitioned.sql`, `docs/DECISIONS.md` |
| 2 | Ingestion, watermark, incremental, Raw Zone | `ingestion/` |
| 3 | Transform, Medallion Bronze/Silver/Gold | `pipeline/load_bronze.py`, `sql/silver/`, `sql/gold/` |
| 4 | Ingestion tool (Airbyte), sync mode | `docs/ARCHITECTURE.md` (Airbyte chạy trên VM, cấu hình trên UI) |
| 5 | Data modeling: grain, fact, dimension, star | `sql/silver/` (5 bảng), `sql/gold/` (4 bảng) |

Thư mục `pipeline/` nối các bước lại. Thư mục `sql/checks/` chứa các câu kiểm tra dữ liệu.

## Chạy

```bash
cp .env.example .env        # điền giá trị, không commit
make setup
make test

make ingest DATE=2026-10-01   # Postgres -> Raw Zone
make bronze DATE=2026-10-01   # Raw Zone -> Bronze (append)
make silver                   # Bronze -> Silver
make gold                     # Silver -> Gold
make check                    # grain, amount, đối chiếu Gold với Silver
make daily DATE=2026-10-01    # chạy cả chuỗi trên

uv run python -m pipeline.run_sql gold --dry-run   # chỉ in bytes processed
```

Cần trước: project GCP, bucket GCS, ba dataset (`stylehub_bronze`, `stylehub_silver`, `stylehub_gold`) và service account có quyền GCS + BigQuery.

## Lưu ý

- Tên cột trong `sql/silver/` suy từ đề BTVN và slide. Hãy đối chiếu với schema thật trong BigQuery (đặc biệt `users` và `shipments`) trước khi chạy.
- Nếu Bronze do Airbyte nạp thì cột metadata là `_airbyte_extracted_at`, không phải `_ingested_at`. Đổi ở các file `sql/silver/`.
- Muốn mở rộng sang dbt, Airflow, Spark: xem [docs/EXTENDING.md](docs/EXTENDING.md).
- Dataset StyleHub là của khóa học. Repo chỉ chứa code tự dựng lại, không commit `secrets/`, `.env`, key GCP, dữ liệu CSV.
