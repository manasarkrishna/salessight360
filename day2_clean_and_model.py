"""
SalesSight 360 — Day 2: Cleaning + Star Schema Modeling
---------------------------------------------------------
Reads the raw messy CSVs from Day 1, cleans them, and loads a proper
star schema into a SQLite database (salessight360.db):

    FACT
      fact_opportunities   (grain: one row per opportunity)
      fact_payments        (grain: one row per payment/order)

    DIMENSIONS
      dim_rep
      dim_region
      dim_product
      dim_channel
      dim_date              (one row per calendar date used in the model)

Also writes a QA log (data/clean/qa_log.txt) documenting exactly what was
fixed and how many rows were affected — this is gold for your README and
for interview conversations ("walk me through your data cleaning").

Run:  python3 day2_clean_and_model.py
"""

import pandas as pd
import numpy as np
import sqlite3
import os
from datetime import datetime

RAW_DIR = "data/raw"
CLEAN_DIR = "data/clean"
DB_PATH = "data/clean/salessight360.db"
os.makedirs(CLEAN_DIR, exist_ok=True)

qa_log = []
def log(msg):
    print(msg)
    qa_log.append(msg)

# ---------------------------------------------------------------------------
# LOAD RAW
# ---------------------------------------------------------------------------
reps = pd.read_csv(f"{RAW_DIR}/reps.csv")
products = pd.read_csv(f"{RAW_DIR}/products.csv")
opps = pd.read_csv(f"{RAW_DIR}/leads_opportunities.csv")
payments = pd.read_csv(f"{RAW_DIR}/orders_payments.csv")

log(f"Loaded raw rows -> reps:{len(reps)} products:{len(products)} "
    f"opportunities:{len(opps)} payments:{len(payments)}")

# ---------------------------------------------------------------------------
# 1. DEDUPE OPPORTUNITIES
# ---------------------------------------------------------------------------
before = len(opps)
opps = opps.drop_duplicates(subset="opp_id", keep="first")
log(f"Removed {before - len(opps)} duplicate opportunity rows (exact opp_id dupes)")

# ---------------------------------------------------------------------------
# 2. STANDARDIZE REGION (messy free text -> canonical dimension)
# ---------------------------------------------------------------------------
def canon_region(raw):
    if pd.isna(raw):
        return None
    r = str(raw).strip().lower().rstrip(".")
    mapping = {
        "north": "North", "n": "North",
        "south": "South", "s": "South",
        "east": "East", "e": "East",
        "west": "West", "w": "West",
        "central": "Central", "centrl": "Central",  # catches the typo
    }
    return mapping.get(r, r.title())

opps["region"] = opps["region_raw"].apply(canon_region)

missing_region = opps["region"].isna().sum()
# fill missing region from the rep's home_region (a defensible, documented rule)
rep_region_map = reps.set_index("rep_id")["home_region"].to_dict()
opps["region"] = opps.apply(
    lambda r: rep_region_map.get(r["rep_id"], "Unknown") if pd.isna(r["region"]) else r["region"],
    axis=1,
)
log(f"Standardized region text into 5 canonical values; "
    f"filled {missing_region} missing regions using the rep's home region")

# ---------------------------------------------------------------------------
# 3. NORMALIZE DATES (mixed formats -> ISO)
# ---------------------------------------------------------------------------
def parse_mixed_date(val):
    if pd.isna(val):
        return pd.NaT
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(str(val), fmt).date()
        except ValueError:
            continue
    return pd.NaT

opps["created_date"] = opps["created_date"].apply(parse_mixed_date)
opps["close_date"] = opps["close_date"].apply(parse_mixed_date)
log("Normalized created_date / close_date from 3 mixed formats into ISO dates")

# ---------------------------------------------------------------------------
# 4. FIX / FLAG BAD DEAL VALUES
# ---------------------------------------------------------------------------
neg_count = (opps["deal_value"] < 0).sum()
zero_count = (opps["deal_value"] == 0).sum()
opps["deal_value_flag"] = np.where(opps["deal_value"] <= 0, "REVIEW", "OK")
opps["deal_value"] = opps["deal_value"].abs()  # correct sign, keep flagged for QA visibility
log(f"Flagged {neg_count} negative and {zero_count} zero deal values as REVIEW "
    f"(kept, corrected sign, not silently dropped)")

# ---------------------------------------------------------------------------
# 5. PAYMENTS: DROP ORPHANS (opp_id with no matching opportunity)
# ---------------------------------------------------------------------------
before = len(payments)
valid_opp_ids = set(opps["opp_id"])
orphans = payments[~payments["opp_id"].isin(valid_opp_ids)]
payments = payments[payments["opp_id"].isin(valid_opp_ids)]
log(f"Removed {len(orphans)} orphan payment rows referencing a non-existent opp_id "
    f"(saved to data/clean/orphan_payments.csv for audit trail)")
orphans.to_csv(f"{CLEAN_DIR}/orphan_payments.csv", index=False)

payments["payment_date"] = payments["payment_date"].apply(parse_mixed_date)

# ---------------------------------------------------------------------------
# 6. BUILD DIMENSIONS
# ---------------------------------------------------------------------------
dim_region = pd.DataFrame({"region_id": range(1, 6),
                            "region_name": ["North", "South", "East", "West", "Central"]})

dim_rep = reps.rename(columns={"home_region": "region_name"}).copy()
dim_rep = dim_rep.merge(dim_region, on="region_name", how="left")
dim_rep = dim_rep[["rep_id", "rep_name", "region_id", "hire_date"]]

dim_product = products.copy()

dim_channel = pd.DataFrame({
    "channel_id": range(1, 6),
    "channel_name": ["Outbound", "Inbound", "Referral", "Partner", "Web Signup"],
})

all_dates = pd.concat([opps["created_date"], opps["close_date"], payments["payment_date"]]).dropna().unique()
dim_date = pd.DataFrame({"date": sorted(all_dates)})
dim_date["date"] = pd.to_datetime(dim_date["date"])
dim_date["date_id"] = dim_date["date"].dt.strftime("%Y%m%d").astype(int)
dim_date["year"] = dim_date["date"].dt.year
dim_date["month"] = dim_date["date"].dt.month
dim_date["month_name"] = dim_date["date"].dt.strftime("%b")
dim_date["quarter"] = dim_date["date"].dt.quarter

# ---------------------------------------------------------------------------
# 7. BUILD FACT TABLES (map text keys -> surrogate ids)
# ---------------------------------------------------------------------------
region_id_map = dim_region.set_index("region_name")["region_id"].to_dict()
channel_id_map = dim_channel.set_index("channel_name")["channel_id"].to_dict()
date_id_map = dim_date.set_index(dim_date["date"].dt.date)["date_id"].to_dict()

fact_opps = opps.copy()
fact_opps["region_id"] = fact_opps["region"].map(region_id_map)
fact_opps["channel_id"] = fact_opps["channel"].map(channel_id_map)
fact_opps["created_date_id"] = fact_opps["created_date"].map(date_id_map)
fact_opps["close_date_id"] = fact_opps["close_date"].map(date_id_map)
fact_opps = fact_opps[[
    "opp_id", "rep_id", "product_id", "region_id", "channel_id",
    "stage", "deal_value", "deal_value_flag", "created_date_id", "close_date_id",
]]

fact_payments = payments.copy()
fact_payments["payment_date_id"] = fact_payments["payment_date"].map(date_id_map)
fact_payments = fact_payments[["order_id", "opp_id", "amount", "payment_status", "payment_date_id"]]

# ---------------------------------------------------------------------------
# 8. LOAD INTO SQLITE
# ---------------------------------------------------------------------------
if os.path.exists(DB_PATH):
    os.remove(DB_PATH)
conn = sqlite3.connect(DB_PATH)

dim_region.to_sql("dim_region", conn, index=False)
dim_rep.to_sql("dim_rep", conn, index=False)
dim_product.to_sql("dim_product", conn, index=False)
dim_channel.to_sql("dim_channel", conn, index=False)
dim_date.drop(columns=["date"]).to_sql("dim_date", conn, index=False)
fact_opps.to_sql("fact_opportunities", conn, index=False)
fact_payments.to_sql("fact_payments", conn, index=False)
conn.close()

log(f"Loaded star schema into {DB_PATH}: "
    f"5 dimension tables + fact_opportunities ({len(fact_opps)} rows) "
    f"+ fact_payments ({len(fact_payments)} rows)")

# also keep clean CSVs for the Pandas/notebook layer later
fact_opps.to_csv(f"{CLEAN_DIR}/fact_opportunities.csv", index=False)
fact_payments.to_csv(f"{CLEAN_DIR}/fact_payments.csv", index=False)
dim_rep.to_csv(f"{CLEAN_DIR}/dim_rep.csv", index=False)
dim_region.to_csv(f"{CLEAN_DIR}/dim_region.csv", index=False)
dim_product.to_csv(f"{CLEAN_DIR}/dim_product.csv", index=False)
dim_channel.to_csv(f"{CLEAN_DIR}/dim_channel.csv", index=False)
dim_date.to_csv(f"{CLEAN_DIR}/dim_date.csv", index=False)

with open(f"{CLEAN_DIR}/qa_log.txt", "w") as f:
    f.write("\n".join(qa_log))

print("\nDay 2 complete. Clean star schema written to", DB_PATH)
