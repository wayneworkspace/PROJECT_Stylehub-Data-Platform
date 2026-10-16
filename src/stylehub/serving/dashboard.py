"""Pipeline monitoring dashboard: how healthy the daily runs are and how fresh Bronze is.

It only reads BigQuery (pipeline_runs and the Bronze tables). The two queries are the files in
src/stylehub/sql/serving/.

Usage (PowerShell):
    docker compose --env-file secrets/.env --profile serving up --build
    then open http://localhost:8501
Or without Docker: uv run --extra serving streamlit run src/stylehub/serving/dashboard.py
"""

import pandas as pd
import streamlit as st

from stylehub.common.bq import query_config
from stylehub.common.clients import bq_client
from stylehub.common.config import SQL_DIR, settings
from stylehub.common.sql import render_sql

STALE_AFTER_HOURS = 26  # a daily load plus a little room


@st.cache_data(ttl=300)  # BigQuery is asked at most every 5 minutes
def read(sql_file: str) -> pd.DataFrame:
    cfg = settings()
    sql = render_sql(SQL_DIR / "serving" / sql_file, cfg)
    return bq_client(cfg).query(sql, job_config=query_config(cfg)).to_dataframe()


st.title("StyleHub pipeline")

runs = read("01_pipeline_health.sql")
failed = runs[runs["status"] == "failed"]
col_runs, col_failed = st.columns(2)
col_runs.metric("Steps in the last 14 days", len(runs))
col_failed.metric("Failed steps", len(failed))

st.subheader("Data freshness (Bronze)")
fresh = read("02_data_freshness.sql")
st.dataframe(fresh, hide_index=True)
for row in fresh[fresh["hours_old"] > STALE_AFTER_HOURS].itertuples():
    st.warning(f"{row.table_name} was loaded {row.hours_old} hours ago")

st.subheader("Duration per step (seconds)")
st.bar_chart(runs, x="started_at", y="duration_seconds", color="step")

st.subheader("Runs")
st.dataframe(runs, hide_index=True)
