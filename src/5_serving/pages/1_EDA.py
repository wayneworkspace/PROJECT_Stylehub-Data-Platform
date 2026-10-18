"""Streamlit EDA page for Postgres Silver order items, Buổi 16 method."""

import sys
from importlib import import_module
from pathlib import Path

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

# Streamlit runs this file by path; add the project root.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
get_logger = import_module("src.0_utils.logger").get_logger

eda = import_module("src.5_serving.eda")
read = import_module("src.5_serving.reader").read
log = get_logger(__name__)

SAMPLE_ROWS = 5000  # Altair draws at most this many points

st.title("EDA: order items, last 90 days")
raw = read("03_eda_order_items.sql")
if raw.empty:
    st.info("No order items in the last 90 days yet. Run the pg branch first.")
    st.stop()

# 1. Overview and audit, on exact Decimal values.
st.header("1. Data quality")
st.caption(f"{len(raw):,} rows, {raw.shape[1]} columns")
st.dataframe(eda.quality_report(raw))
dups = eda.duplicate_counts(raw, ["id"])
issues = eda.data_issues(raw)
col_dup, col_issue = st.columns(2)
col_dup.write(pd.Series(dups, name="duplicates"))
col_issue.write(pd.Series(issues, name="rows"))

# 2. Types: floats for statistics, then smaller dtypes.
df = raw.astype(dict.fromkeys(eda.NUMERIC_COLUMNS, "float64"))
df["order_date"] = pd.to_datetime(df["order_date"])
before = eda.memory_mb(df)
df = eda.optimize_dtypes(df)
log.info("EDA rows %s, memory %s MB -> %s MB", len(df), before, eda.memory_mb(df))
st.caption(f"Memory {before} MB before, {eda.memory_mb(df)} MB after dtype optimization")

st.header("2. Statistics")
st.dataframe(df[eda.NUMERIC_COLUMNS].describe().round(2))

st.header("3. Distribution of item amount")
counts, edges = np.histogram(df["amount"].dropna(), bins=40)
bins = pd.DataFrame({"start": edges[:-1], "end": edges[1:], "count": counts})
stats = pd.DataFrame(
    {"stat": ["mean", "median"], "value": [df["amount"].mean(), df["amount"].median()]}
)
bars = alt.Chart(bins).mark_bar().encode(x="start:Q", x2="end:Q", y="count:Q")
lines = alt.Chart(stats).mark_rule(strokeWidth=2).encode(x="value:Q", color="stat:N")
st.altair_chart(bars + lines, width="stretch")

sample = df.sample(min(len(df), SAMPLE_ROWS), random_state=0)
st.subheader(f"Amount by category (random sample of {len(sample):,} items)")
box = alt.Chart(sample).mark_boxplot().encode(x="category:N", y="amount:Q")
st.altair_chart(box, width="stretch")

st.header("4. Revenue over time and by group")
st.line_chart(df.groupby("order_date")["amount"].sum())
st.bar_chart(eda.kpis_by(df, ["category"])["revenue"])
st.subheader("KPIs by category and state (top 20)")
st.dataframe(eda.kpis_by(df, ["category", "state"]).head(20))

st.header("5. Correlation")
corr = eda.correlation(df, eda.NUMERIC_COLUMNS).stack().rename("corr").reset_index()
heatmap = (
    alt.Chart(corr)
    .mark_rect()
    .encode(
        x="level_0:N",
        y="level_1:N",
        color=alt.Color("corr:Q", scale=alt.Scale(scheme="redyellowgreen", domain=[-1, 1])),
    )
)
st.altair_chart(heatmap + heatmap.mark_text().encode(text="corr:Q", color=alt.value("black")))

st.header("6. Outliers (IQR 1.5)")
outlier_cols = ["sale_price", "quantity", "amount"]
st.dataframe(eda.outlier_summary(df, outlier_cols))
capped = eda.cap_outliers(df, outlier_cols)
st.caption("Max before and after capping; the row count stays the same.")
st.dataframe(pd.DataFrame({"before": df[outlier_cols].max(), "after": capped[outlier_cols].max()}))
