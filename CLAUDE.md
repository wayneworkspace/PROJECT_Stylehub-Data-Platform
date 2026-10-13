# CLAUDE.md — quy tắc cho AI khi viết code trong repo này

## Dự án
StyleHub Data Platform trên GCP, xây theo giáo trình 5 buổi.
Source (Postgres + API) → Raw Zone (GCS) → Bronze → Silver (fact/dim) → Gold (BigQuery).
Hiện chỉ dùng stack của giáo trình: Python, SQL, GCS, BigQuery, Airbyte.
dbt, Airflow, Spark là bước mở rộng sau: không thêm vào trừ khi được yêu cầu (xem `docs/EXTENDING.md`).

## Nguyên tắc chung
- Code đơn giản, dễ đọc. Ưu tiên rõ ràng hơn thông minh. Không trừu tượng hóa sớm.
- Một file một nhiệm vụ. Hàm ngắn, tên mô tả đúng việc nó làm.
- Chia thư mục theo tầng: `ingestion/`, `sql/{bronze,silver,gold,checks}`, `pipeline/`.
- Không thêm tính năng ngoài yêu cầu. Không viết code "phòng hờ" chưa cần.
- Commit theo Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`).

## Hợp đồng giữa các tầng (không phá, để mở rộng không phải viết lại)
- Mỗi bước chạy được độc lập bằng CLI có `--date`, và an toàn khi chạy lại.
- Tên dataset và grain của từng bảng là hợp đồng. Đổi grain thì phải cập nhật `docs/ARCHITECTURE.md`.
- Logic nghiệp vụ nằm trong file SQL, không nằm trong code Python.
- Cấu hình chỉ đọc từ `pipeline/config.py` (biến môi trường), không rải hằng số khắp nơi.

## Ingestion
- Ingestion chỉ có MỘT nhiệm vụ: extract và ghi raw. Không transform, không làm sạch.
- Raw Zone chỉ thêm file, không ghi đè: `raw/stylehub/<bảng>/date=<YYYY-MM-DD>/batch_id=<id>/<bảng>.parquet`.
- Mọi file raw có 3 cột metadata: `_ingested_at`, `_source`, `_batch_id`.
- Chạy lại phải an toàn: cùng đầu vào thì số id khác nhau không đổi.

## SQL
- Viết bằng CTE. Không dùng subquery.
- File đặt tên có số thứ tự (`01_`, `02_`) theo thứ tự phụ thuộc. Dùng `${project}`, `${bronze}`, `${silver}`, `${gold}`.
- Bronze: chỉ thêm dòng, giữ mọi phiên bản. Silver: mỗi id một dòng mới nhất, ép đúng kiểu, ghi grain ở đầu file.
- Gold: chứa rule nghiệp vụ (ví dụ bỏ đơn `Cancelled`). Rule đổi thì sửa Gold, Silver giữ nguyên.
- Mỗi bảng Silver có check grain trong `sql/checks/`. Gold có check đối chiếu tổng với Silver.
- Bảng lớn (events) phải có `PARTITION BY` và `CLUSTER BY`; ghi lý do và số đo vào `docs/DECISIONS.md`.

## Bảo mật
- Không commit: `secrets/`, `.env`, key JSON của GCP, HMAC key, mật khẩu DB, dữ liệu CSV thô.
- Firewall VM Airbyte giới hạn theo IP của mình, không mở `0.0.0.0/0`. Tắt VM khi không dùng.
- Dataset StyleHub là của khóa học: chỉ đưa lên GitHub phần tự dựng lại, không đưa tài liệu hay code mẫu của giảng viên.

## Trước khi báo xong
- `make lint` và `make test` phải qua.
- Cập nhật README/docs nếu đổi hành vi.
