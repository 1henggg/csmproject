from io import BytesIO
from pathlib import Path
import re

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

APP_DIR = Path(__file__).resolve().parent
DEFAULT_CSV = APP_DIR / "supply_chain_dataset1.csv"

st.set_page_config(
    page_title="Semiconductor SCM Dashboard",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)


def normalize_name(name: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9]+", "_", str(name).strip().lower())
    return name.strip("_")


@st.cache_data(show_spinner="Loading and preparing supply-chain data…")
def load_data(file_bytes: bytes) -> pd.DataFrame:
    raw = pd.read_csv(BytesIO(file_bytes), encoding="utf-8-sig")
    df = raw.copy()
    df.columns = [normalize_name(c) for c in df.columns]

    # Accept both the original Kaggle-style headers (SKU, Demand, Lead Time…)
    # and the standardized headers used in the earlier notebook/app.
    aliases = {
        "sku": "sku_id",
        "warehouse": "warehouse_id",
        "supplier": "supplier_id",
        "inventory": "inventory_level",
        "demand": "units_sold",
        "forecast": "demand_forecast",
        "lead_time": "supplier_lead_time_days",
        "stockout": "stockout_flag",
        "promotion": "promotion_flag",
    }
    for old, new in aliases.items():
        if old in df.columns and new not in df.columns:
            df = df.rename(columns={old: new})

    required = [
        "date", "sku_id", "warehouse_id", "units_sold", "inventory_level",
        "supplier_lead_time_days", "reorder_point", "unit_cost", "unit_price",
        "stockout_flag", "demand_forecast",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            "CSV 缺少必要欄位：" + ", ".join(missing)
            + "。請確認使用 supply_chain_dataset1.csv，且欄位包含 Date、SKU、Warehouse、Demand、Inventory、Lead Time、Reorder Point、Unit Cost、Unit Price、Stockout、Forecast。"
        )

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    numeric_cols = [
        "units_sold", "inventory_level", "supplier_lead_time_days", "reorder_point",
        "unit_cost", "unit_price", "stockout_flag", "demand_forecast",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df["sku_id"] = df["sku_id"].astype("string").str.strip()
    df["warehouse_id"] = df["warehouse_id"].astype("string").str.strip()
    df = df.dropna(subset=["date", "sku_id", "warehouse_id"]).drop_duplicates().copy()
    df = df.sort_values(["sku_id", "warehouse_id", "date"])

    df["inventory_value"] = df["inventory_level"] * df["unit_cost"]
    df["below_rop"] = df["inventory_level"] < df["reorder_point"]
    df["forecast_accuracy"] = (
        1 - (df["units_sold"] - df["demand_forecast"]).abs()
        / df["units_sold"].where(df["units_sold"] > 0)
    ).clip(lower=0, upper=1)

    # Calculate rolling demand before the date filter so the first days in a
    # selected range can still use the preceding 7 observations.
    demand_group = df.groupby(["sku_id", "warehouse_id"], sort=False)["units_sold"]
    df["avg_daily_demand_7d"] = demand_group.transform(
        lambda s: s.rolling(7, min_periods=7).mean()
    )
    df["days_of_supply"] = (
        df["inventory_level"] / df["avg_daily_demand_7d"].where(df["avg_daily_demand_7d"] > 0)
    )
    return df


def add_abc_class(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    sku_abc = (
        df.groupby("sku_id", as_index=False)
        .agg(annual_demand=("units_sold", "sum"), unit_cost=("unit_cost", "mean"))
    )
    sku_abc["consumption_value"] = sku_abc["annual_demand"] * sku_abc["unit_cost"]
    sku_abc = sku_abc.sort_values("consumption_value", ascending=False).reset_index(drop=True)
    total_value = sku_abc["consumption_value"].sum()
    if total_value > 0:
        sku_abc["cumulative_value_pct"] = sku_abc["consumption_value"].cumsum() / total_value * 100
        sku_abc["abc_class"] = pd.cut(
            sku_abc["cumulative_value_pct"],
            bins=[0, 80, 95, 100.000001],
            labels=["A", "B", "C"],
            include_lowest=True,
        ).astype("string")
        # Keep a defined class even for unusual rounding or a single-SKU dataset.
        sku_abc["abc_class"] = sku_abc["abc_class"].fillna("C")
    else:
        sku_abc["cumulative_value_pct"] = 0.0
        sku_abc["abc_class"] = "C"
    return sku_abc, sku_abc[["sku_id", "abc_class"]]


st.title("Semiconductor Supply Chain Dashboard")
st.caption("Inventory visibility · Demand vs. forecast · Reorder-point monitoring · ABC segmentation")

with st.sidebar:
    st.header("Dashboard filters")
    uploaded = st.file_uploader("Optional: upload a different CSV", type=["csv"])

if uploaded is not None:
    source_bytes = uploaded.getvalue()
    source_label = uploaded.name
elif DEFAULT_CSV.exists():
    source_bytes = DEFAULT_CSV.read_bytes()
    source_label = DEFAULT_CSV.name
else:
    st.info(
        "Dashboard 資料尚未載入。若要讓公開連結開啟後直接顯示圖表，請將 "
        "`supply_chain_dataset1.csv` 放在 `app.py` 同一個 GitHub 資料夾；"
        "也可以先在左側上傳 CSV 進行測試。"
    )
    st.stop()

try:
    df = load_data(source_bytes)
except Exception as exc:
    st.error(f"資料載入失敗：{exc}")
    st.stop()

sku_abc, abc_lookup = add_abc_class(df)
df = df.merge(abc_lookup, on="sku_id", how="left", validate="many_to_one")

with st.sidebar:
    st.caption(f"Data source: {source_label}")
    min_date = df["date"].min().date()
    max_date = df["date"].max().date()
    selected_dates = st.date_input(
        "Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date
    )
    if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
        start_date, end_date = selected_dates
    else:
        start_date = end_date = selected_dates

    warehouse_options = sorted(df["warehouse_id"].dropna().astype(str).unique().tolist())
    selected_warehouses = st.multiselect(
        "Warehouse", warehouse_options, default=warehouse_options
    )
    sku_options = sorted(df["sku_id"].dropna().astype(str).unique().tolist())
    selected_skus = st.multiselect("SKU", sku_options, default=sku_options)
    selected_abc = st.multiselect("ABC class", ["A", "B", "C"], default=["A", "B", "C"])

filtered = df[
    df["date"].dt.date.between(start_date, end_date)
    & df["warehouse_id"].astype(str).isin(selected_warehouses)
    & df["sku_id"].astype(str).isin(selected_skus)
    & df["abc_class"].astype(str).isin(selected_abc)
].copy()

if filtered.empty:
    st.warning("目前篩選條件沒有資料，請調整日期、Warehouse、SKU 或 ABC class。")
    st.stop()

st.caption(
    f"Showing {filtered['date'].min().date()} to {filtered['date'].max().date()} · "
    f"{len(filtered):,} daily records · ABC class is assigned using each SKU's full-dataset consumption value."
)

# KPI row
k1, k2, k3, k4 = st.columns(4)
k1.metric("SKU Count", f"{filtered['sku_id'].nunique():,}")
k2.metric("Below ROP Rate", f"{filtered['below_rop'].mean():.1%}")
k3.metric("Stockout Flag Rate", f"{filtered['stockout_flag'].mean():.2%}")
avg_dos = filtered["days_of_supply"].replace([np.inf, -np.inf], np.nan).mean()
k4.metric("Avg. Days of Supply", "N/A" if pd.isna(avg_dos) else f"{avg_dos:.1f} days")

k5, k6 = st.columns(2)
valid_accuracy = filtered["forecast_accuracy"].dropna()
k5.metric("Avg. Forecast Accuracy", "N/A" if valid_accuracy.empty else f"{valid_accuracy.mean():.1%}")
inv_value = filtered["inventory_value"].mean()
k6.metric("Avg. Inventory Value", "N/A" if pd.isna(inv_value) else f"{inv_value:,.2f}")

st.divider()
left, right = st.columns(2)

with left:
    st.subheader("Demand vs. Forecast")
    trend = (
        filtered.groupby("date", as_index=False)
        .agg(actual_demand=("units_sold", "sum"), forecast_demand=("demand_forecast", "sum"))
        .sort_values("date")
    )
    trend_long = trend.melt(
        id_vars="date", value_vars=["actual_demand", "forecast_demand"],
        var_name="series", value_name="units"
    )
    trend_long["series"] = trend_long["series"].map(
        {"actual_demand": "Actual demand", "forecast_demand": "Forecast demand"}
    )
    fig_trend = px.line(
        trend_long, x="date", y="units", color="series", markers=False,
        labels={"date": "Date", "units": "Units", "series": "Series"},
    )
    fig_trend.update_layout(legend_title_text="", margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig_trend, use_container_width=True)

with right:
    st.subheader("Stockout Flag Rate by Warehouse")
    warehouse_summary = (
        filtered.groupby("warehouse_id", as_index=False)
        .agg(stockout_flag_rate=("stockout_flag", "mean"), below_rop_rate=("below_rop", "mean"))
        .sort_values("stockout_flag_rate", ascending=False)
    )
    fig_wh = px.bar(
        warehouse_summary, x="warehouse_id", y="stockout_flag_rate",
        labels={"warehouse_id": "Warehouse", "stockout_flag_rate": "Stockout flag rate"},
        text=warehouse_summary["stockout_flag_rate"].map(lambda x: f"{x:.1%}"),
    )
    fig_wh.update_traces(textposition="outside", cliponaxis=False)
    fig_wh.update_yaxes(tickformat=".0%")
    fig_wh.update_layout(showlegend=False, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig_wh, use_container_width=True)

left2, right2 = st.columns(2)
with left2:
    st.subheader("SKU Count by ABC Class")
    abc_filtered = filtered[["sku_id", "abc_class"]].drop_duplicates()
    abc_summary = (
        abc_filtered.groupby("abc_class", as_index=False)
        .agg(sku_count=("sku_id", "nunique"))
    )
    abc_summary["abc_class"] = pd.Categorical(abc_summary["abc_class"], ["A", "B", "C"], ordered=True)
    abc_summary = abc_summary.sort_values("abc_class")
    fig_abc = px.bar(
        abc_summary, x="abc_class", y="sku_count", color="abc_class",
        labels={"abc_class": "ABC class", "sku_count": "Number of SKUs"},
        text="sku_count",
    )
    fig_abc.update_traces(textposition="outside", showlegend=False, cliponaxis=False)
    fig_abc.update_layout(showlegend=False, margin=dict(l=10, r=10, t=20, b=10))
    st.plotly_chart(fig_abc, use_container_width=True)

with right2:
    st.subheader("Inventory Status — Latest Selected Date")
    latest = (
        filtered.sort_values("date")
        .groupby(["sku_id", "warehouse_id"], as_index=False, group_keys=False)
        .tail(1)
        .copy()
    )
    latest["status"] = np.where(latest["below_rop"], "Below ROP", "At/Above ROP")
    latest = latest.sort_values(
        ["below_rop", "days_of_supply"], ascending=[False, True], na_position="last"
    )
    display_cols = [
        "sku_id", "warehouse_id", "abc_class", "status", "inventory_level",
        "reorder_point", "days_of_supply", "supplier_lead_time_days",
    ]
    table = latest[display_cols].rename(columns={
        "sku_id": "SKU", "warehouse_id": "Warehouse", "abc_class": "ABC",
        "inventory_level": "Inventory", "reorder_point": "Reorder Point",
        "days_of_supply": "Days of Supply", "supplier_lead_time_days": "Lead Time (days)",
    })
    st.dataframe(table.head(25).round(2), use_container_width=True, hide_index=True)
    st.caption("Table shows the latest available record for each SKU × Warehouse within the selected date range.")

with st.expander("Metric definitions & assumptions"):
    st.markdown(
        "- **Below ROP Rate** = daily records where Inventory < Reorder Point ÷ valid daily records.\n"
        "- **Stockout Flag Rate** = average of the dataset-provided Stockout Flag; its interpretation depends on the source dataset's definition.\n"
        "- **Days of Supply** = Inventory ÷ rolling 7-observation average daily demand, calculated separately for each SKU × Warehouse.\n"
        "- **Forecast Accuracy** = max(0, min(1, 1 − |Actual − Forecast| ÷ Actual)); records with Actual demand = 0 are excluded. This is a project-defined metric, not a universal standard.\n"
        "- **ABC class** uses SKU consumption value = total demand × average unit cost, with cumulative value cutoffs at 80% and 95%. Class is calculated on the full loaded dataset; other charts respond to filters."
    )

st.caption("Portfolio project · Public sample dataset · Metrics are exploratory and should not be interpreted as validated operational forecasts.")
