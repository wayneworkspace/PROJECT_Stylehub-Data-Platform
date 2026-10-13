"""Incremental load một bảng từ Postgres vào Raw Zone (Buổi 2).

Chỉ extract và ghi raw. Watermark là một cột thời gian, có lookback để bắt dòng đến trễ.
Chạy lại chỉ tạo thêm file mới (append-only). Bronze giữ hết, Silver bỏ dòng trùng.

Cột watermark của order_items phải chọn bằng data thật: kiểm tra khi đơn đổi trạng thái thì
updated_at của order_items có đổi không (xem docs/DECISIONS.md mục 2).

Dùng: python -m ingestion.incremental --table orders --date 2026-10-01
"""

import argparse
import os
from datetime import date, datetime, timedelta

import pandas as pd
import psycopg2
from dotenv import load_dotenv

from ingestion.raw_writer import write_raw

# bảng -> cột watermark. Thêm bảng mới ở đây, không sửa logic bên dưới.
WATERMARK = {
    "orders": "updated_at",
    "order_items": "updated_at",
}
INCREMENTAL_TABLES = tuple(WATERMARK)
LOOKBACK_DAYS = 1


def window_for(data_date: date, lookback_days: int = LOOKBACK_DAYS) -> tuple[datetime, datetime]:
    """Khoảng [start, end) cần đọc cho một ngày dữ liệu."""
    start = datetime.combine(data_date - timedelta(days=lookback_days), datetime.min.time())
    end = datetime.combine(data_date + timedelta(days=1), datetime.min.time())
    return start, end


def connect():
    return psycopg2.connect(
        host=os.environ["PG_HOST"],
        port=os.environ.get("PG_PORT", "5432"),
        dbname=os.environ["PG_DATABASE"],
        user=os.environ["PG_USER"],
        password=os.environ["PG_PASSWORD"],
    )


def extract_day(table: str, data_date: date) -> pd.DataFrame:
    if table not in WATERMARK:
        raise ValueError(f"Bảng chưa cấu hình watermark: {table}")
    column = WATERMARK[table]
    start, end = window_for(data_date)
    query = f"SELECT * FROM {table} WHERE {column} >= %s AND {column} < %s"
    with connect() as conn:
        return pd.read_sql(query, conn, params=(start, end))


def ingest_table(table: str, data_date: str) -> str:
    load_dotenv()
    df = extract_day(table, date.fromisoformat(data_date))
    uri = write_raw(df, table, data_date, source="postgres")
    return f"{table} {data_date}: {len(df)} dòng -> {uri}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--table", required=True, choices=INCREMENTAL_TABLES)
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    args = parser.parse_args()
    print(ingest_table(args.table, args.date))


if __name__ == "__main__":
    main()
