"""
SalesSight 360 — Day 2: Cleaning + Star Schema Modeling (POSTGRES VERSION)
----------------------------------------------------------------------------
Same cleaning logic as the SQLite version, but loads into a real Postgres
database with proper PRIMARY KEY / FOREIGN KEY constraints — so when you
open this in pgAdmin4, "Tools > ERD Tool" will draw you a real relationship
diagram, which is exactly the kind of screenshot that goes in your README.

BEFORE RUNNING:
  1. In pgAdmin4 (or psql), create an empty database, e.g.:
       CREATE DATABASE salessight360;
  2. Edit the PG_CONFIG dict below with your actual local credentials
     (the ones you set up when you installed Postgres / did the churn project).
  3. pip install psycopg2-binary sqlalchemy --break-system-packages

Run:  python3 day2_clean_and_model_postgres.py
"""

import pandas as pd
import numpy as np
import os
from datetime import datetime
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# EDIT THESE to match your local Postgres / pgAdmin4 setup
# ---------------------------------------------------------------------------
PG_CONFIG = {
    "user": "postgres",
    "password": "postman123",      # <-- change to your actual password
    "host": "localhost",
    "port": "5432",
    "dbname": "salessight360",   # <-- create this database first in pgAdmin4
}

RAW_DIR = "data/raw"
CLEAN_DIR = "data/clean"
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
        "central": "Central", "centrl": "Central",
    }
    return mapping.get(r, r.title())

opps["region"] = opps["region_raw"].apply(canon_region)
missing_region = opps["region"].isna().sum()
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
opps["deal_value"] = opps["deal_value"].abs()
log(f"Flagged {neg_count} negative and {zero_count} zero deal values as REVIEW "
    f"(kept, corrected sign, not silently dropped)")

# ---------------------------------------------------------------------------
# 5. PAYMENTS: DROP ORPHANS
# ---------------------------------------------------------------------------
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
# 7. BUILD FACT TABLES
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
# Postgres integer columns can't hold NaN — convert to pandas nullable Int64
fact_opps["close_date_id"] = fact_opps["close_date_id"].astype("Int64")
fact_opps["created_date_id"] = fact_opps["created_date_id"].astype("Int64")

fact_payments = payments.copy()
fact_payments["payment_date_id"] = fact_payments["payment_date"].map(date_id_map)
fact_payments = fact_payments[["order_id", "opp_id", "amount", "payment_status", "payment_date_id"]]
fact_payments["payment_date_id"] = fact_payments["payment_date_id"].astype("Int64")

# ---------------------------------------------------------------------------
# 8. CREATE SCHEMA IN POSTGRES (real PK/FK constraints for the ERD view)
# ---------------------------------------------------------------------------
conn_str = (f"postgresql+psycopg2://{PG_CONFIG['user']}:{PG_CONFIG['password']}"
            f"@{PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['dbname']}")
engine = create_engine(conn_str)

DDL = """
DROP TABLE IF EXISTS fact_payments, fact_opportunities, dim_rep, dim_date, dim_channel, dim_product, dim_region CASCADE;

CREATE TABLE dim_region (
    region_id   INTEGER PRIMARY KEY,
    region_name TEXT NOT NULL
);

CREATE TABLE dim_product (
    product_id   TEXT PRIMARY KEY,
    product_name TEXT NOT NULL,
    category     TEXT,
    unit_price   NUMERIC
);

CREATE TABLE dim_channel (
    channel_id   INTEGER PRIMARY KEY,
    channel_name TEXT NOT NULL
);

CREATE TABLE dim_date (
    date_id    INTEGER PRIMARY KEY,
    year       INTEGER,
    month      INTEGER,
    month_name TEXT,
    quarter    INTEGER
);

CREATE TABLE dim_rep (
    rep_id     TEXT PRIMARY KEY,
    rep_name   TEXT NOT NULL,
    region_id  INTEGER REFERENCES dim_region(region_id),
    hire_date  DATE
);

CREATE TABLE fact_opportunities (
    opp_id           TEXT PRIMARY KEY,
    rep_id           TEXT REFERENCES dim_rep(rep_id),
    product_id       TEXT REFERENCES dim_product(product_id),
    region_id        INTEGER REFERENCES dim_region(region_id),
    channel_id       INTEGER REFERENCES dim_channel(channel_id),
    stage            TEXT NOT NULL,
    deal_value       NUMERIC,
    deal_value_flag  TEXT,
    created_date_id  INTEGER REFERENCES dim_date(date_id),
    close_date_id    INTEGER REFERENCES dim_date(date_id)
);

CREATE TABLE fact_payments (
    order_id         TEXT PRIMARY KEY,
    opp_id           TEXT REFERENCES fact_opportunities(opp_id),
    amount           NUMERIC,
    payment_status   TEXT,
    payment_date_id  INTEGER REFERENCES dim_date(date_id)
);
"""

with engine.begin() as connection:
    for statement in DDL.split(";"):
        if statement.strip():
            connection.execute(text(statement))

log("Created star schema DDL in Postgres with PK/FK constraints "
    "(open pgAdmin4 -> your db -> Tools -> ERD Tool to see the diagram)")

# ---------------------------------------------------------------------------
# 9. LOAD DATA (tables already exist, so append)
# ---------------------------------------------------------------------------
dim_region.to_sql("dim_region", engine, if_exists="append", index=False)
dim_product.to_sql("dim_product", engine, if_exists="append", index=False)
dim_channel.to_sql("dim_channel", engine, if_exists="append", index=False)
dim_date.drop(columns=["date"]).to_sql("dim_date", engine, if_exists="append", index=False)
dim_rep.to_sql("dim_rep", engine, if_exists="append", index=False)
fact_opps.to_sql("fact_opportunities", engine, if_exists="append", index=False)
fact_payments.to_sql("fact_payments", engine, if_exists="append", index=False)

log(f"Loaded star schema into Postgres db '{PG_CONFIG['dbname']}': "
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

print(f"\nDay 2 complete. Open pgAdmin4 -> Servers -> your server -> Databases -> "
      f"{PG_CONFIG['dbname']} -> Schemas -> public -> Tables to see the result.")
