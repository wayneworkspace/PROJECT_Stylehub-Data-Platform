"""Streamlit page: pipeline run health and Bronze data freshness."""

import sys
from importlib import import_module
from pathlib import Path

import streamlit as st

# Streamlit runs this file by path; add the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
read = import_module("src.5_serving.reader").read

STALE_AFTER_HOURS = 26  # a daily load plus a little room

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
