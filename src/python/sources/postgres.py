"""Read data from the StyleHub Postgres database.

Connection settings come from the environment (PG_HOST, PG_DATABASE, PG_USER, PG_PASSWORD and
optionally PG_PORT and PG_SSLMODE). Call common.config.load_env() first so secrets/.env is read.
"""

import os
from contextlib import closing

import pandas as pd
import psycopg2


def connect() -> psycopg2.extensions.connection:
    """Open a new connection. The caller must close it."""
    return psycopg2.connect(
        host=os.environ["PG_HOST"],
        port=os.environ.get("PG_PORT", "5432"),
        dbname=os.environ["PG_DATABASE"],
        user=os.environ["PG_USER"],
        password=os.environ["PG_PASSWORD"],
        # "prefer" is the libpq default: encrypt when the server can, so a local Docker
        # Postgres still works. Set PG_SSLMODE=require for a server that demands TLS.
        sslmode=os.environ.get("PG_SSLMODE", "prefer"),
    )


def fetch_dataframe(query: str, params: tuple = ()) -> pd.DataFrame:
    """Run one query and return the rows as a DataFrame."""
    # closing() really closes the connection. psycopg2's own "with" only ends the transaction.
    with closing(connect()) as conn, conn.cursor() as cur:
        cur.execute(query, params)
        columns = [col.name for col in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=columns)
