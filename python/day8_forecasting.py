"""
SalesSight 360 — Day 8: Forecasting Logic
---------------------------------------------
Two deliverables:

  1. WEIGHTED PIPELINE FORECAST — for every currently open deal:
         expected_value = deal_value x win_probability(current_stage)
     summed by region/rep, this is "how much revenue we realistically expect"
     from the pipeline as it stands today, as opposed to naive pipeline_value
     (which just sums every open deal at 100%, wildly overstating reality).

  2. FORECAST ACCURACY BACKTEST — a documented limitation and how we work
     around it: our CRM export has no point-in-time snapshots (we don't know
     what stage a deal was in on any past date, only its final stage). So we
     can't truly answer "what would we have forecast last March?" A real
     CRM with stage-history logs (or a nightly snapshot table) could.
     What we CAN do, and what real analysts do when historical snapshots
     don't exist: approximate using each closed deal's LAST KNOWN STAGE
     before it closed (Closed Won deals must have passed through Proposal;
     Closed Lost deals' last stage comes from Day 4's reconstructed
     stage-progression model) and ask "if we'd applied today's win-rate
     model to that stage, how close would the prediction have been?"
     This is a legitimate backtesting technique for validating whether your
     probability weights are calibrated — say this explicitly in your README,
     it's a mature thing to know and state rather than gloss over.

STAGE WIN PROBABILITIES (a documented business assumption — tune these to
match your own funnel's realized win rates for a stronger writeup):
    Lead        -> 10%
    Qualified   -> 30%
    Proposal    -> 60%
    Closed Won  -> 100%
    Closed Lost -> 0%

BEFORE RUNNING: edit PG_CONFIG below.

Outputs:
  data/kpis/weighted_pipeline_forecast.csv   (forward-looking, by region)
  data/kpis/forecast_accuracy_backtest.csv   (predicted vs actual, by month)

Run: python3 day8_forecasting.py
"""

import pandas as pd
import numpy as np
import os
from sqlalchemy import create_engine

PG_CONFIG = {
    "user": "postgres",
    "password": "password",      # <-- change to your actual password
    "host": "localhost",
    "port": "5432",
    "dbname": "salessight360",
}

OUT_DIR = "data/kpis"
os.makedirs(OUT_DIR, exist_ok=True)
np.random.seed(42)  # must match Day 4/6 seed to reconstruct the same stage progression

conn_str = (f"postgresql+psycopg2://{PG_CONFIG['user']}:{PG_CONFIG['password']}"
            f"@{PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['dbname']}")
engine = create_engine(conn_str)

WIN_PROB = {"Lead": 0.10, "Qualified": 0.30, "Proposal": 0.60, "Closed Won": 1.00, "Closed Lost": 0.00}

# ---------------------------------------------------------------------------
# 1. WEIGHTED PIPELINE FORECAST (open deals only)
# ---------------------------------------------------------------------------
opps = pd.read_sql_query("""
    SELECT o.opp_id, o.stage, o.deal_value, o.region_id, o.rep_id, o.created_date_id,
           r.region_name, rep.rep_name
    FROM fact_opportunities o
    JOIN dim_region r ON o.region_id = r.region_id
    JOIN dim_rep rep ON o.rep_id = rep.rep_id
""", engine)

open_deals = opps[~opps["stage"].isin(["Closed Won", "Closed Lost"])].copy()
open_deals["win_prob"] = open_deals["stage"].map(WIN_PROB)
open_deals["expected_value"] = open_deals["deal_value"] * open_deals["win_prob"]

forecast_by_region = open_deals.groupby("region_name").agg(
    open_deal_count=("opp_id", "count"),
    naive_pipeline_value=("deal_value", "sum"),
    weighted_forecast=("expected_value", "sum"),
).reset_index()
forecast_by_region["naive_pipeline_value"] = forecast_by_region["naive_pipeline_value"].round(2)
forecast_by_region["weighted_forecast"] = forecast_by_region["weighted_forecast"].round(2)
forecast_by_region["overstatement_pct"] = round(
    100 * (forecast_by_region["naive_pipeline_value"] - forecast_by_region["weighted_forecast"])
    / forecast_by_region["naive_pipeline_value"], 1
)
forecast_by_region = forecast_by_region.sort_values("weighted_forecast", ascending=False)
forecast_by_region.to_csv(f"{OUT_DIR}/weighted_pipeline_forecast.csv", index=False)

print("Weighted pipeline forecast by region:")
print(forecast_by_region.to_string(index=False))
print(f"\n^ naive pipeline sums every open deal at 100% — see how much that overstates "
      f"reality (overstatement_pct column) vs. the probability-weighted number.")

# ---------------------------------------------------------------------------
# 2. FORECAST ACCURACY BACKTEST (documented approximation — see docstring)
# ---------------------------------------------------------------------------
closed = opps[opps["stage"].isin(["Closed Won", "Closed Lost"])].copy()

# reconstruct last-known-stage exactly as Day 4 did (same seed -> same assignment)
lost_mask = closed["stage"] == "Closed Lost"
lost_at_stage = np.random.choice(
    ["Lead", "Qualified", "Proposal"], size=lost_mask.sum(), p=[0.45, 0.35, 0.20]
)
closed.loc[lost_mask, "last_known_stage"] = lost_at_stage
closed.loc[~lost_mask, "last_known_stage"] = "Proposal"  # Closed Won must have passed Proposal

closed["predicted_value"] = closed["deal_value"] * closed["last_known_stage"].map(WIN_PROB)
closed["actual_value"] = np.where(closed["stage"] == "Closed Won", closed["deal_value"], 0)

close_dates = pd.read_sql_query("""
    SELECT o.opp_id, d.year, d.month
    FROM fact_opportunities o JOIN dim_date d ON o.close_date_id = d.date_id
""", engine)
closed = closed.merge(close_dates, on="opp_id", how="left")

backtest = closed.groupby(["year", "month"]).agg(
    predicted_total=("predicted_value", "sum"),
    actual_total=("actual_value", "sum"),
).reset_index()
backtest["predicted_total"] = backtest["predicted_total"].round(2)
backtest["actual_total"] = backtest["actual_total"].round(2)
backtest["abs_error"] = (backtest["predicted_total"] - backtest["actual_total"]).abs().round(2)
backtest["pct_error"] = round(100 * backtest["abs_error"] / backtest["actual_total"], 1)
backtest = backtest.sort_values(["year", "month"])
backtest.to_csv(f"{OUT_DIR}/forecast_accuracy_backtest.csv", index=False)

overall_mape = backtest["pct_error"].replace([np.inf, -np.inf], np.nan).mean()
print(f"\nForecast accuracy backtest (last 6 months):")
print(backtest.tail(6).to_string(index=False))
print(f"\nOverall mean absolute % error (MAPE) across all months: {overall_mape:.1f}%")

engine.dispose()
print("\nDay 8 complete. Outputs saved to", OUT_DIR)
