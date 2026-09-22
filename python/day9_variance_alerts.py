"""
SalesSight 360 — Day 9: Variance & Alerting Logic
------------------------------------------------------
FIRST ATTEMPT (kept here as an honest record — this is worth telling in an
interview): the standard industry heuristic is coverage_ratio = open_pipeline
/ target, flagging anything below ~3x. Running that on this dataset put
EVERY region and EVERY rep at 30x-50x+ coverage — useless, not because the
business is healthy, but because "open pipeline" here is an unbounded stock
(every open deal ever created across 14 months of history) being compared
against a single month's target (a rate). The 3x-4x heuristic only works
when pipeline is scoped to deals expected to close within the target period
— which requires an expected-close-date field we don't have on open deals.

FIX: since Day 8 already built a probability-weighted forecast (expected
converting value, not just raw dollars), that number is already on the same
footing as a revenue target — so a ratio of weighted_forecast / target
naturally centers around 1.0 (expected to just hit target) rather than
needing an arbitrary multiplier. Threshold: ratio < 1.0 = expected shortfall.

TARGETS: no quota table exists in the raw export (real CRMs pull this from
a separate planning tool), so we approximate target as 110% of trailing
3-month average Closed-Won revenue, EXCLUDING the current in-progress month
(including it crashed the average, since "today" is mid-month).

Outputs:
  data/kpis/coverage_by_region.csv
  data/kpis/coverage_by_rep.csv
  data/kpis/at_risk_alerts.csv   <- the flagged list for the dashboard

Run: python3 day9_variance_alerts.py
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

COVERAGE_THRESHOLD = 1.0   # weighted forecast should at least equal target
WIN_PROB = {"Lead": 0.10, "Qualified": 0.30, "Proposal": 0.60}

conn_str = (f"postgresql+psycopg2://{PG_CONFIG['user']}:{PG_CONFIG['password']}"
            f"@{PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['dbname']}")
engine = create_engine(conn_str)

opps = pd.read_sql_query("""
    SELECT o.opp_id, o.stage, o.deal_value, o.region_id, o.rep_id, o.close_date_id,
           r.region_name, rep.rep_name
    FROM fact_opportunities o
    JOIN dim_region r ON o.region_id = r.region_id
    JOIN dim_rep rep ON o.rep_id = rep.rep_id
""", engine)

close_dates = pd.read_sql_query("SELECT date_id, year, month FROM dim_date", engine)
opps = opps.merge(close_dates, left_on="close_date_id", right_on="date_id", how="left")

open_deals = opps[opps["stage"].isin(WIN_PROB.keys())].copy()
open_deals["expected_value"] = open_deals["deal_value"] * open_deals["stage"].map(WIN_PROB)

won = opps[opps["stage"] == "Closed Won"].copy()
won["period"] = won["year"] * 12 + won["month"]

# ---------------------------------------------------------------------------
# 2. Trailing-3-month average won revenue -> target -> coverage ratio, by region
# ---------------------------------------------------------------------------
def trailing_avg_target(df, group_col):
    monthly = df.groupby([group_col, "period"])["deal_value"].sum().reset_index()
    all_periods = sorted(monthly["period"].unique())
    # The most recent period is "today" mid-month — necessarily partial and
    # therefore artificially low. Including it would crash the target and
    # make every coverage ratio look falsely healthy (this is exactly what
    # happened on the first run of this script — worth knowing as a general
    # pattern: always drop the current in-progress period before computing
    # a trailing-average baseline).
    full_periods = all_periods[:-1] if len(all_periods) > 1 else all_periods
    recent_periods = full_periods[-3:]
    recent = monthly[monthly["period"].isin(recent_periods)]
    avg_monthly = recent.groupby(group_col)["deal_value"].mean()
    target = (avg_monthly * 1.10).round(2)   # documented rule: 110% of trailing run-rate
    return target

region_target = trailing_avg_target(won, "region_name")
open_by_region = open_deals.groupby("region_name")["expected_value"].sum().round(2)

coverage_region = pd.DataFrame({
    "weighted_forecast": open_by_region,
    "monthly_target": region_target,
}).dropna()
coverage_region["coverage_ratio"] = round(coverage_region["weighted_forecast"] / coverage_region["monthly_target"], 2)
coverage_region["at_risk"] = coverage_region["coverage_ratio"] < COVERAGE_THRESHOLD
coverage_region = coverage_region.reset_index().rename(columns={"index": "region_name"})
coverage_region = coverage_region.sort_values("coverage_ratio")
coverage_region.to_csv(f"{OUT_DIR}/coverage_by_region.csv", index=False)

print(f"Weighted-forecast coverage ratio by region (threshold = {COVERAGE_THRESHOLD}x):")
print(coverage_region.to_string(index=False))

# ---------------------------------------------------------------------------
# 3. Same thing by rep — this is what actually drives 1:1 coaching conversations
# ---------------------------------------------------------------------------
rep_target = trailing_avg_target(won, "rep_name")
open_by_rep = open_deals.groupby("rep_name")["expected_value"].sum().round(2)

coverage_rep = pd.DataFrame({
    "weighted_forecast": open_by_rep,
    "monthly_target": rep_target,
}).dropna()
coverage_rep["coverage_ratio"] = round(coverage_rep["weighted_forecast"] / coverage_rep["monthly_target"], 2)
coverage_rep["at_risk"] = coverage_rep["coverage_ratio"] < COVERAGE_THRESHOLD
coverage_rep = coverage_rep.reset_index().rename(columns={"index": "rep_name"})
coverage_rep = coverage_rep.sort_values("coverage_ratio")
coverage_rep.to_csv(f"{OUT_DIR}/coverage_by_rep.csv", index=False)

n_at_risk_reps = coverage_rep["at_risk"].sum()
print(f"\n{n_at_risk_reps} of {len(coverage_rep)} reps are below {COVERAGE_THRESHOLD}x coverage "
      f"(absolute threshold — flags an expected shortfall)")

# ---------------------------------------------------------------------------
# 3b. RELATIVE risk flag — bottom quartile by coverage ratio
# ---------------------------------------------------------------------------
# Honest caveat, worth stating in your README: because open deals have no
# expected-close-date field, weighted_forecast accumulates EVERY open deal
# across the full ~14-month history, not just deals likely to close this
# period — so it's structurally always far above one month's target, and
# the absolute 1.0x threshold above will basically never fire on this
# dataset (0 of 40 reps did). That's a data-scoping limitation, not evidence
# the business is safe. The actionable alternative: flag reps in the BOTTOM
# QUARTILE of coverage relative to their peers — still useful for "who needs
# a pipeline-generation push this week" even without perfect time-scoping.
q25 = coverage_rep["coverage_ratio"].quantile(0.25)
coverage_rep["relative_risk"] = coverage_rep["coverage_ratio"] <= q25
coverage_rep.to_csv(f"{OUT_DIR}/coverage_by_rep.csv", index=False)

n_relative_risk = coverage_rep["relative_risk"].sum()
print(f"{n_relative_risk} reps sit in the bottom quartile of coverage relative to peers "
      f"(coverage_ratio <= {q25:.2f}x) — these are the realistic 'needs attention' list "
      f"given the data we have.")

# ---------------------------------------------------------------------------
# 4. Consolidated alert list — what the dashboard's "Variance & Alerts" page reads
# ---------------------------------------------------------------------------
alerts = coverage_rep[coverage_rep["relative_risk"]].copy()
alerts["alert_type"] = "Bottom-quartile pipeline coverage"
alerts["message"] = alerts.apply(
    lambda r: f"{r['rep_name']}: {r['coverage_ratio']}x coverage (bottom quartile vs peers, "
              f"median is {coverage_rep['coverage_ratio'].median():.1f}x) — candidate for a "
              f"pipeline-generation push",
    axis=1,
)
alerts = alerts[["rep_name", "coverage_ratio", "weighted_forecast", "monthly_target", "alert_type", "message"]]
alerts = alerts.sort_values("coverage_ratio")
alerts.to_csv(f"{OUT_DIR}/at_risk_alerts.csv", index=False)

print(f"\nBottom-quartile reps flagged for pipeline-generation attention:")
print(alerts[["rep_name", "coverage_ratio"]].to_string(index=False))

engine.dispose()
print("\nDay 9 complete. Outputs saved to", OUT_DIR)
