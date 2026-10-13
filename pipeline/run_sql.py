"""Chạy các file SQL của một tầng theo thứ tự tên file (01_, 02_, ...).

Dùng:
    python -m pipeline.run_sql silver
    python -m pipeline.run_sql gold --dry-run     # chỉ in bytes processed (Buổi 1)
    python -m pipeline.run_sql silver --file 04_fact_order_items.sql
"""

import argparse

from google.cloud import bigquery

from pipeline.config import SQL_DIR, render_sql, settings

LAYERS = ("bronze", "silver", "gold")


def run_layer(layer: str, dry_run: bool = False, only_file: str | None = None) -> None:
    client = bigquery.Client(project=settings()["project"])
    paths = sorted((SQL_DIR / layer).glob("*.sql"))
    if only_file:
        paths = [p for p in paths if p.name == only_file]
        if not paths:
            raise SystemExit(f"Không thấy {only_file} trong sql/{layer}/")

    for path in paths:
        config = bigquery.QueryJobConfig(dry_run=dry_run, use_query_cache=False)
        job = client.query(render_sql(path), job_config=config)
        if dry_run:
            print(f"{layer}/{path.name}: {job.total_bytes_processed:,} bytes")
        else:
            job.result()
            print(f"{layer}/{path.name}: xong")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("layer", choices=LAYERS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--file")
    args = parser.parse_args()
    run_layer(args.layer, dry_run=args.dry_run, only_file=args.file)


if __name__ == "__main__":
    main()
