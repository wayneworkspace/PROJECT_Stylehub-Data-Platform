"""Cached BigQuery reads shared by the Streamlit pages."""

from importlib import import_module

import pandas as pd
import streamlit as st

bq = import_module("src.1_source.bq")
config = import_module("src.1_source.config")


@st.cache_data(ttl=300)  # BigQuery is asked at most every 5 minutes
def read(sql_file: str) -> pd.DataFrame:
    cfg = config.settings()
    sql = bq.render_sql(config.SQL_DIR / "serving" / sql_file, cfg)
    return config.bq_client(cfg).query(sql, job_config=bq.query_config(cfg)).to_dataframe()
