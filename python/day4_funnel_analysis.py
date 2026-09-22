"""
SalesSight 360 — Day 4: Funnel & Conversion Analytics
---------------------------------------------------------
Our fact_opportunities table only stores the FINAL stage an opportunity
reached (Lead / Qualified / Proposal / Closed Won / Closed Lost) — it doesn't
natively record "how far a lost deal got before dying." Real CRMs (Salesforce,
HubSpot) DO track this via stage-history logs, so we simulate that layer here:
each Closed Lost opportunity is assigned the stage it fell out at, weighted
so that more deals die earlier (Lead) than later (Proposal) — matching how
real funnels behave.

This is a modeling decision worth stating explicitly in your README/interview:
"the raw CRM export only had a final-stage snapshot, so I reconstructed a
stage-progression model using a documented, weighted assumption" — that
sentence alone signals more maturity than a static bar chart ever will.

Outputs:
  data/kpis/funnel_overall.csv
  data/kpis/funnel_by_channel.csv
  data/kpis/funnel_by_region.csv
  data/kpis/drop_off_rates.csv

BEFORE RUNNING: edit PG_CONFIG below to match your local pgAdmin4 setup
(same credentials used in day2_clean_and_model_postgres.py).

Run: python3 day4_funnel_analysis.py
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
np.random.seed(42)

conn_str = (f"postgresql+psycopg2://{PG_CONFIG['user']}:{PG_CONFIG['password']}"
            f"@{PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['dbname']}")
engine = create_engine(conn_str)

opps = pd.read_sql_query("""
    SELECT o.opp_id, o.stage, o.region_id, o.channel_id,
           r.region_name, c.channel_name
    FROM fact_opportunities o
    JOIN dim_region r ON o.region_id = r.region_id
    JOIN dim_channel c ON o.channel_id = c.channel_id
""", engine)

STAGE_ORDER = {"Lead": 1, "Qualified": 2, "Proposal": 3, "Closed Won": 4}

# ---------------------------------------------------------------------------
# 1. Reconstruct "how far did each Closed Lost deal get" (documented weights)
# ---------------------------------------------------------------------------
lost_mask = opps["stage"] == "Closed Lost"
n_lost = lost_mask.sum()
lost_at = np.random.choice([1, 2, 3], size=n_lost, p=[0.45, 0.35, 0.20])
opps.loc[lost_mask, "max_stage_reached"] = lost_at

# for anything not lost, map directly
not_lost_mask = ~lost_mask
opps.loc[not_lost_mask, "max_stage_reached"] = opps.loc[not_lost_mask, "stage"].map(STAGE_ORDER)
opps["max_stage_reached"] = opps["max_stage_reached"].astype(int)

# persist this back to the DB as a real column so it's queryable with plain SQL too
opps[["opp_id", "max_stage_reached"]].to_sql("stage_progression", engine, if_exists="replace", index=False)

# ---------------------------------------------------------------------------
# 2. Overall funnel (cumulative — "reached at least this stage")
# ---------------------------------------------------------------------------
funnel_stages = ["Lead", "Qualified", "Proposal", "Closed Won"]
overall_counts = []
for stage_name, stage_num in STAGE_ORDER.items():
    if stage_name == "Closed Won":
        count = (opps["stage"] == "Closed Won").sum()
    else:
        count = (opps["max_stage_reached"] >= stage_num).sum()
    overall_counts.append({"stage": stage_name, "count": count})

funnel_overall = pd.DataFrame(overall_counts)
funnel_overall["pct_of_top"] = round(100 * funnel_overall["count"] / funnel_overall["count"].iloc[0], 1)
funnel_overall["drop_off_from_prev"] = funnel_overall["count"].diff().fillna(0).abs()
funnel_overall["drop_off_rate_pct"] = round(
    100 * funnel_overall["drop_off_from_prev"] / funnel_overall["count"].shift(1), 1
)
funnel_overall.to_csv(f"{OUT_DIR}/funnel_overall.csv", index=False)

# ---------------------------------------------------------------------------
# 3. Funnel segmented by channel (source) and by region
# ---------------------------------------------------------------------------
def build_segmented_funnel(segment_col):
    rows = []
    for seg_val, grp in opps.groupby(segment_col):
        for stage_name, stage_num in STAGE_ORDER.items():
            if stage_name == "Closed Won":
                count = (grp["stage"] == "Closed Won").sum()
            else:
                count = (grp["max_stage_reached"] >= stage_num).sum()
            rows.append({segment_col: seg_val, "stage": stage_name, "count": count})
    df = pd.DataFrame(rows)
    df["pct_of_entry"] = df.groupby(segment_col)["count"].transform(lambda s: round(100 * s / s.iloc[0], 1))
    return df

funnel_by_channel = build_segmented_funnel("channel_name")
funnel_by_region = build_segmented_funnel("region_name")
funnel_by_channel.to_csv(f"{OUT_DIR}/funnel_by_channel.csv", index=False)
funnel_by_region.to_csv(f"{OUT_DIR}/funnel_by_region.csv", index=False)

# ---------------------------------------------------------------------------
# 4. Stage-by-stage drop-off rate, segmented by channel — this is the table
#    that answers "where in the funnel is each channel actually leaking?"
# ---------------------------------------------------------------------------
drop_rows = []
for seg_val, grp in funnel_by_channel.groupby("channel_name"):
    grp = grp.sort_values("count", ascending=False).reset_index(drop=True)
    for i in range(1, len(grp)):
        prev_count = grp.loc[i - 1, "count"]
        cur_count = grp.loc[i, "count"]
        drop_pct = round(100 * (prev_count - cur_count) / prev_count, 1) if prev_count else None
        drop_rows.append({
            "channel_name": seg_val,
            "from_stage": grp.loc[i - 1, "stage"],
            "to_stage": grp.loc[i, "stage"],
            "drop_off_rate_pct": drop_pct,
        })
drop_off_rates = pd.DataFrame(drop_rows)
drop_off_rates.to_csv(f"{OUT_DIR}/drop_off_rates.csv", index=False)

engine.dispose()

print("Overall funnel:\n", funnel_overall.to_string(index=False))
print("\nBiggest channel-level drop-offs (top 5):")
print(drop_off_rates.sort_values("drop_off_rate_pct", ascending=False).head(5).to_string(index=False))
print("\nDay 4 complete. Funnel outputs saved to", OUT_DIR)
