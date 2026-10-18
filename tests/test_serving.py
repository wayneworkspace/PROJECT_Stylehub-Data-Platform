"""Serving stage: EDA helpers, the cached reader and both Streamlit pages."""

from importlib import import_module
from types import SimpleNamespace as NS

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

config = import_module("src.1_source.config")
eda = import_module("src.5_serving.eda")
reader = import_module("src.5_serving.reader")

PAGES = config.ROOT / "src" / "5_serving"


def items(rows: int = 40) -> pd.DataFrame:
    """Order items shaped like 03_eda_order_items.sql."""
    return pd.DataFrame(
        {
            "id": range(rows),
            "order_id": [i // 2 for i in range(rows)],
            "user_id": [i % 7 for i in range(rows)],
            "status": ["Complete"] * rows,
            "sale_price": [10.0 + i for i in range(rows)],
            "quantity": [1 + i % 3 for i in range(rows)],
            "amount": [(10.0 + i) * (1 + i % 3) for i in range(rows)],
            "cost": [5.0] * rows,
            "total_cost": [5.0 * (1 + i % 3) for i in range(rows)],
            "order_date": pd.date_range("2026-10-01", periods=rows, freq="D").date,
            "category": ["Jeans", "Tops"] * (rows // 2),
            "state": ["CA", "NY", "TX", "WA"] * (rows // 4),
            "traffic_source": ["Search"] * rows,
            "age": [20 + i for i in range(rows)],
        }
    )


@pytest.fixture
def fake_read(monkeypatch):
    frames: dict[str, pd.DataFrame] = {}
    monkeypatch.setattr(reader, "read", lambda sql_file: frames[sql_file])
    return frames


def test_optimize_dtypes_memory_and_correlation() -> None:
    df = pd.DataFrame({"n": [1, 2, 3, 4], "f": [1.0, 2.0, 3.0, 4.5], "t": ["a", "a", "a", "a"]})
    small = eda.optimize_dtypes(df)
    assert str(small["n"].dtype) == "int8"
    assert str(small["f"].dtype) == "float32"
    assert str(small["t"].dtype) == "category"
    assert eda.memory_mb(small) <= eda.memory_mb(df)
    corr = eda.correlation(df, ["n", "f"])
    assert corr.loc["f", "n"] > 0.9
    assert pd.isna(corr.loc["n", "f"])  # upper triangle is masked


def test_reader_renders_sql_and_queries(monkeypatch) -> None:
    cfg = config.Settings(GCP_PROJECT_ID="proj", GCS_BUCKET="bucket")
    asked: list[str] = []
    client = NS(query=lambda sql, job_config: asked.append(sql) or NS(to_dataframe=pd.DataFrame))
    monkeypatch.setattr(config, "settings", lambda: cfg)
    monkeypatch.setattr(config, "bq_client", lambda cfg: client)
    reader.read.clear()
    assert reader.read("01_pipeline_health.sql").empty
    assert "proj.stylehub_ops.pipeline_runs" in asked[0]


def test_dashboard_page_warns_on_stale_tables(fake_read) -> None:
    fake_read["01_pipeline_health.sql"] = pd.DataFrame(
        {
            "status": ["success", "failed"],
            "started_at": pd.to_datetime(["2026-10-01", "2026-10-02"]),
            "duration_seconds": [1.0, 2.0],
            "step": ["ingest", "bronze"],
        }
    )
    fake_read["02_data_freshness.sql"] = pd.DataFrame(
        {"table_name": ["orders", "users"], "hours_old": [2, 40]}
    )
    app = AppTest.from_file(str(PAGES / "dashboard.py"), default_timeout=60).run()
    assert not app.exception
    assert [m.value for m in app.metric] == ["2", "1"]
    assert "users was loaded 40 hours ago" in app.warning[0].value


def test_eda_page_runs_every_section(fake_read) -> None:
    fake_read["03_eda_order_items.sql"] = items()
    app = AppTest.from_file(str(PAGES / "pages" / "1_EDA.py"), default_timeout=120).run()
    assert not app.exception
    assert len(app.header) == 6
    assert app.caption[0].value == "40 rows, 14 columns"


def test_eda_page_stops_without_data(fake_read) -> None:
    fake_read["03_eda_order_items.sql"] = items().iloc[0:0]
    app = AppTest.from_file(str(PAGES / "pages" / "1_EDA.py"), default_timeout=60).run()
    assert not app.exception
    assert "No order items" in app.info[0].value
