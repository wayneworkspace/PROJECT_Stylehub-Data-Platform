# Mở rộng sau này

Repo được chia để thêm công cụ mới mà không viết lại. Phần giữ nguyên là **hợp đồng**: tên dataset (`stylehub_bronze`, `stylehub_silver`, `stylehub_gold`), tên bảng và grain từng bảng, đường dẫn Raw Zone.

## dbt (thay `sql/silver`, `sql/gold`, `sql/checks`)

1. Tạo thư mục `dbt/`. Khai báo `sources` trỏ vào `stylehub_bronze`.
2. Mỗi file `sql/silver/NN_ten.sql` thành một model `models/silver/ten.sql`: bỏ dòng `CREATE OR REPLACE TABLE`, giữ phần `SELECT`, đổi `` `${project}.${bronze}.x` `` thành `{{ source('bronze', 'x') }}` và `` `${project}.${silver}.x` `` thành `{{ ref('x') }}`. Thứ tự `01_`, `02_` không còn cần vì dbt tự suy ra từ `ref`.
3. Mỗi file `sql/checks/` thành test: check grain thành `unique` + `not_null`, các check còn lại thành singular test (cùng cấu trúc "trả về dòng nếu lỗi").
4. Xóa `make silver`, `make gold`, `make check` và thay bằng `dbt build`. `ingestion/` và `load_bronze` không đổi.

## Airflow (thay `pipeline/run_daily.py`)

1. `STEPS` trong `run_daily.py` đã là danh sách bước: ingest → bronze → silver → gold → checks. Mỗi bước thành một task.
2. Task gọi đúng các CLI hiện có (`python -m ingestion.incremental --date {{ ds }}`, `python -m pipeline.load_bronze --date {{ ds }}`...). Không cần sửa logic bên trong.
3. Retry và cảnh báo cấu hình ở Airflow, không viết trong code Python.
4. Nếu đã dùng dbt thì task silver/gold/checks gộp thành `dbt build`.

## Spark (cho xử lý lớn, ví dụ `events`)

1. Thêm `spark/`. Đọc Parquet từ Raw Zone (cùng đường dẫn `raw/stylehub/events/...`), ghi kết quả thành bảng ở Silver hoặc Gold.
2. Chạy trên Dataproc. Giữ nguyên tên bảng đầu ra để các tầng sau không đổi.
3. Chỉ chuyển sang Spark khi SQL trên BigQuery không còn phù hợp (xử lý phức tạp, chi phí quét lớn). Ghi số đo trước và sau vào `docs/DECISIONS.md`.

## Thay Python ingestion bằng Airbyte

`ingestion/` và Airbyte cùng ghi vào Raw Zone/Bronze. Đổi nguồn cho một bảng bằng cách tắt bước ingest của bảng đó trong `run_daily.py`. Nếu Airbyte nạp thẳng Bronze thì đổi `_ingested_at` thành `_airbyte_extracted_at` trong `sql/silver/`.
