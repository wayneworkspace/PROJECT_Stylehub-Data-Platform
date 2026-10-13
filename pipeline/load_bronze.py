"""Nạp file Raw của một ngày vào Bronze. Chỉ thêm dòng (append), không ghi đè.

Chạy lại cùng một ngày sẽ thêm dòng trùng vào Bronze. Đó là chủ ý: Bronze giữ mọi lần ingest,
Silver bỏ trùng.

Dùng: python -m pipeline.load_bronze --date 2026-10-01 [--table orders]
"""

import argparse

from google.cloud import bigquery

from pipeline.config import RAW_DIR, settings

TABLES = ("orders", "order_items", "products", "users", "shipments")


def load_day(table: str, data_date: str) -> int:
    s = settings()
    raw_dir = RAW_DIR.get(table, table)
    uri = f"gs://{s['bucket']}/{s['raw_prefix']}/{raw_dir}/date={data_date}/*"
    table_id = f"{s['project']}.{s['bronze']}.{table}"

    client = bigquery.Client(project=s["project"])
    config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.PARQUET,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    job = client.load_table_from_uri(uri, table_id, job_config=config)
    job.result()
    return job.output_rows or 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--table", choices=TABLES)
    args = parser.parse_args()

    for table in [args.table] if args.table else TABLES:
        print(f"{table} {args.date}: {load_day(table, args.date)} dòng -> Bronze")


if __name__ == "__main__":
    main()
