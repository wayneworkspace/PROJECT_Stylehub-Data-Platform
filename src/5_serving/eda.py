"""EDA helpers from the Buổi 16 method: quality, duplicates, outliers, KPIs."""

import numpy as np
import pandas as pd

NUMERIC_COLUMNS = ["sale_price", "quantity", "amount", "cost", "total_cost", "age"]


def optimize_dtypes(df: pd.DataFrame, cat_threshold: float = 0.5) -> pd.DataFrame:
    """Downcast numbers and turn low-cardinality text into category."""
    out = df.copy()
    for col in out.select_dtypes(include="integer"):
        out[col] = pd.to_numeric(out[col], downcast="integer")
    for col in out.select_dtypes(include="float"):
        out[col] = pd.to_numeric(out[col], downcast="float")
    for col in out.select_dtypes(include=["object", "string"]):
        if out[col].nunique() / max(len(out), 1) < cat_threshold:
            out[col] = out[col].astype("category")
    return out


def memory_mb(df: pd.DataFrame) -> float:
    return round(df.memory_usage(deep=True).sum() / 1024**2, 2)


def quality_report(df: pd.DataFrame) -> pd.DataFrame:
    """Per column: type, missing count and share, distinct values."""
    missing = df.isna().sum()
    report = pd.DataFrame(
        {
            "dtype": df.dtypes.astype(str),
            "missing": missing,
            "missing_pct": (missing / max(len(df), 1) * 100).round(1),
            "unique": df.nunique(),
        }
    )
    return report.sort_values("missing_pct", ascending=False)


def duplicate_counts(df: pd.DataFrame, keys: list[str]) -> dict[str, int]:
    """Full-row duplicates and duplicates on the business key."""
    return {"full_rows": int(df.duplicated().sum()), "key": int(df.duplicated(keys).sum())}


def data_issues(df: pd.DataFrame) -> dict[str, int]:
    """Rows that break business rules; every count should be zero."""
    checks = {
        "negative amount": df["amount"] < 0,
        "quantity below 1": df["quantity"] < 1,
        "amount != sale_price * quantity": df["amount"] != df["sale_price"] * df["quantity"],
        "sold below cost": df["sale_price"] < df["cost"],
    }
    return {name: int(mask.sum()) for name, mask in checks.items()}


def iqr_bounds(series: pd.Series, multiplier: float = 1.5) -> tuple[float, float]:
    """Lower and upper fence: Q1 - k*IQR and Q3 + k*IQR."""
    q1, q3 = series.quantile([0.25, 0.75])
    iqr = q3 - q1
    return float(q1 - multiplier * iqr), float(q3 + multiplier * iqr)


def outlier_summary(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Fences, outlier count and share for each numeric column."""
    rows = []
    for col in cols:
        data = df[col].dropna().astype(float)
        lower, upper = iqr_bounds(data)
        mask = (data < lower) | (data > upper)
        rows.append(
            {
                "column": col,
                "lower": round(lower, 2),
                "upper": round(upper, 2),
                "n_out": int(mask.sum()),
                "pct_out": round(float(mask.mean() * 100), 1) if len(data) else 0.0,
            }
        )
    return pd.DataFrame(rows).set_index("column")


def zscore_summary(df: pd.DataFrame, cols: list[str], threshold: float = 3.0) -> pd.DataFrame:
    """Outliers by z-score: values more than threshold standard deviations from the mean."""
    rows = []
    for col in cols:
        data = df[col].dropna().astype(float)
        mask = ((data - data.mean()) / data.std()).abs() > threshold  # std 0 gives NaN: none
        rows.append(
            {
                "column": col,
                "n_out": int(mask.sum()),
                "pct_out": round(float(mask.mean() * 100), 1) if len(data) else 0.0,
            }
        )
    return pd.DataFrame(rows).set_index("column")


def cap_outliers(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Clip each column to its fences; the row count does not change."""
    out = df.copy()
    for col in cols:
        lower, upper = iqr_bounds(out[col].dropna().astype(float))
        out[col] = out[col].astype(float).clip(lower=max(0.0, lower), upper=upper)
    return out


def fill_missing(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Flag NULLs in <col>_missing, then fill numbers with the median, the rest with the mode."""
    out = df.copy()
    for col in [c for c in cols if df[c].isna().any() and df[c].notna().any()]:
        out[f"{col}_missing"] = out[col].isna()
        numeric = pd.api.types.is_numeric_dtype(out[col])
        out[col] = out[col].fillna(out[col].median() if numeric else out[col].mode().iloc[0])
    return out


def add_time_features(df: pd.DataFrame, date_col: str = "order_date") -> pd.DataFrame:
    """Year, month and quarter of a datetime column, for grouping."""
    dates = df[date_col].dt
    return df.assign(year=dates.year, month=dates.month, quarter=dates.quarter)


def kpis_by(df: pd.DataFrame, dims: list[str]) -> pd.DataFrame:
    """Revenue, units and customers grouped by one or more dimensions."""
    return (
        df.groupby(dims, observed=True)
        .agg(
            revenue=("amount", "sum"),
            units=("quantity", "sum"),
            customers=("user_id", "nunique"),
        )
        .sort_values("revenue", ascending=False)
    )


def correlation(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """Pearson correlation; the upper triangle is masked like the course heatmap."""
    corr = df[cols].astype(float).corr().round(2)
    return corr.where(np.tril(np.ones(corr.shape, dtype=bool)))


def findings(df: pd.DataFrame, outliers: pd.DataFrame) -> list[str]:
    """Plain-language conclusions from the numbers above, one sentence each."""
    by_category = kpis_by(df, ["category"])["revenue"]
    mean, median = df["amount"].mean(), df["amount"].median()
    corr = correlation(df, NUMERIC_COLUMNS).stack().dropna()  # empty when nothing varies
    corr = corr[corr.index.get_level_values(0) != corr.index.get_level_values(1)].abs()
    missing = [c for c in df.columns if df[c].isna().any()]
    skew = (
        "right-skewed: a few large items pull the mean up" if mean > median else "not right-skewed"
    )
    lines = []
    if not by_category.empty:
        top_share = by_category.iloc[0] / by_category.sum() * 100
        lines.append(
            f"{by_category.index[0]} brings the most revenue: {top_share:.0f}% of the total."
        )
    lines += [
        f"Item amount is {skew} (mean {mean:,.2f}, median {median:,.2f}); "
        "report the median as the typical item.",
        f"{outliers.loc['amount', 'pct_out']}% of items are amount outliers by IQR; "
        "check them before capping, large orders can be real.",
    ]
    if not corr.empty:
        pair = corr.idxmax()
        lines.append(f"Strongest link: {pair[0]} and {pair[1]} (|r| = {corr.max():.2f}).")
    lines.append(
        f"Columns with missing values: {', '.join(missing)}." if missing else "No missing values."
    )
    return lines
