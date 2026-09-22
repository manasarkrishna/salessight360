"""
SalesSight 360 — Day 6: Python / Pandas Layer + Charts
----------------------------------------------------------
Re-does the funnel and cohort logic in pure pandas (tool-flexibility signal —
shows you're not a one-trick SQL analyst), then produces 3 polished charts
for the write-up:

  1. Funnel bar chart (stage-by-stage counts)
  2. Cohort conversion heatmap (the differentiator from Day 5)
  3. Monthly revenue trend line chart

BEFORE RUNNING: edit PG_CONFIG below to match your local pgAdmin4 setup.

Outputs:
  data/charts/funnel_chart.png
  data/charts/cohort_heatmap.png
  data/charts/revenue_trend.png

Run: python3 day6_python_layer.py
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os
from sqlalchemy import create_engine

PG_CONFIG = {
    "user": "postgres",
    "password": "password",      # <-- change to your actual password
    "host": "localhost",
    "port": "5432",
    "dbname": "salessight360",
}

CHART_DIR = "data/charts"
KPI_DIR = "data/kpis"
os.makedirs(CHART_DIR, exist_ok=True)
sns.set_theme(style="whitegrid", palette="deep")

conn_str = (f"postgresql+psycopg2://{PG_CONFIG['user']}:{PG_CONFIG['password']}"
            f"@{PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['dbname']}")
engine = create_engine(conn_str)

# =============================================================================
# PART A — Funnel logic redone in pure pandas (parallel to the SQL/Day-4 version)
# =============================================================================
opps = pd.read_sql_query("""
    SELECT o.opp_id, o.stage, o.region_id, o.channel_id, o.deal_value
    FROM fact_opportunities o
""", engine)

np.random.seed(42)  # same seed as Day 4 -> same reconstructed stage progression
STAGE_ORDER = {"Lead": 1, "Qualified": 2, "Proposal": 3, "Closed Won": 4}

lost_mask = opps["stage"] == "Closed Lost"
lost_at = np.random.choice([1, 2, 3], size=lost_mask.sum(), p=[0.45, 0.35, 0.20])
opps.loc[lost_mask, "max_stage_reached"] = lost_at
opps.loc[~lost_mask, "max_stage_reached"] = opps.loc[~lost_mask, "stage"].map(STAGE_ORDER)
opps["max_stage_reached"] = opps["max_stage_reached"].astype(int)

funnel_counts = {}
for stage_name, stage_num in STAGE_ORDER.items():
    if stage_name == "Closed Won":
        funnel_counts[stage_name] = (opps["stage"] == "Closed Won").sum()
    else:
        funnel_counts[stage_name] = (opps["max_stage_reached"] >= stage_num).sum()

funnel_df = pd.Series(funnel_counts, name="count").reset_index().rename(columns={"index": "stage"})
print("Funnel (pandas):\n", funnel_df.to_string(index=False))

# ---- Chart 1: Funnel bar chart ----
fig, ax = plt.subplots(figsize=(8, 5))
bars = ax.bar(funnel_df["stage"], funnel_df["count"], color=sns.color_palette("Blues_r", len(funnel_df)))
for bar, count in zip(bars, funnel_df["count"]):
    pct = 100 * count / funnel_df["count"].iloc[0]
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 60,
            f"{count:,}\n({pct:.0f}%)", ha="center", fontsize=10)
ax.set_title("Sales Funnel: Lead → Closed Won", fontsize=14, weight="bold")
ax.set_ylabel("Opportunities")
ax.set_ylim(0, funnel_df["count"].max() * 1.15)
sns.despine()
plt.tight_layout()
plt.savefig(f"{CHART_DIR}/funnel_chart.png", dpi=150)
plt.show()
print(f"Saved {CHART_DIR}/funnel_chart.png")

# =============================================================================
# PART B — Cohort heatmap (reads Day 5's output — no need to recompute)
# =============================================================================
pct_matrix = pd.read_csv(f"{KPI_DIR}/cohort_conversion_pct_matrix.csv", index_col=0)
pct_matrix.columns = pct_matrix.columns.astype(int)

fig, ax = plt.subplots(figsize=(12, 7))
sns.heatmap(pct_matrix, annot=True, fmt=".1f", cmap="YlGnBu", cbar_kws={"label": "Cumulative % converted"}, ax=ax)
ax.set_title("Cohort Conversion Rate: % of Leads Converted by Month Since Creation", fontsize=13, weight="bold")
ax.set_xlabel("Months Since Lead Created")
ax.set_ylabel("Acquisition Cohort (Month Created)")
plt.tight_layout()
plt.savefig(f"{CHART_DIR}/cohort_heatmap.png", dpi=150)
plt.show()
print(f"Saved {CHART_DIR}/cohort_heatmap.png")

# =============================================================================
# PART C — Monthly revenue trend (reads Day 3's output)
# =============================================================================
revenue = pd.read_csv(f"{KPI_DIR}/revenue_by_region_month.csv")
monthly_total = revenue.groupby(["year", "month"], as_index=False)["revenue"].sum()
monthly_total["period"] = pd.to_datetime(monthly_total["year"].astype(str) + "-" + monthly_total["month"].astype(str) + "-01")
monthly_total = monthly_total.sort_values("period")

fig, ax = plt.subplots(figsize=(10, 5))
sns.lineplot(data=monthly_total, x="period", y="revenue", marker="o", ax=ax, linewidth=2.5)
ax.set_title("Monthly Revenue Trend", fontsize=14, weight="bold")
ax.set_xlabel("")
ax.set_ylabel("Revenue ($)")
ax.yaxis.set_major_formatter(lambda x, pos: f"${x:,.0f}")
fig.autofmt_xdate()
sns.despine()
plt.tight_layout()
plt.savefig(f"{CHART_DIR}/revenue_trend.png", dpi=150)
plt.show()
print(f"Saved {CHART_DIR}/revenue_trend.png")

engine.dispose()
print("\nDay 6 complete. 3 charts saved to", CHART_DIR)
