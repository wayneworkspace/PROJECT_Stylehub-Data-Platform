"""Chạy các câu kiểm tra trong sql/checks/. Mỗi file trả về 0 dòng nếu đạt, có dòng nếu lỗi.

Dùng: python -m pipeline.checks
"""

import sys

from google.cloud import bigquery

from pipeline.config import SQL_DIR, render_sql, settings


def run_checks() -> bool:
    client = bigquery.Client(project=settings()["project"])
    ok = True
    for path in sorted((SQL_DIR / "checks").glob("*.sql")):
        rows = list(client.query(render_sql(path)).result())
        if rows:
            ok = False
            print(f"LỖI {path.name}:")
            for row in rows:
                print("   ", dict(row))
        else:
            print(f"ĐẠT {path.name}")
    return ok


def main() -> None:
    sys.exit(0 if run_checks() else 1)


if __name__ == "__main__":
    main()
