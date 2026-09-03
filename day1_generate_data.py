"""
SalesSight 360 — Day 1: Synthetic CRM Data Generator
------------------------------------------------------
Generates 3 linked, deliberately messy tables that mimic a real CRM export:

  1. reps_regions_products.csv   -> reps, their home region, products they sell
  2. leads_opportunities.csv     -> the pipeline (lead -> qualified -> proposal -> closed won/lost)
  3. orders_payments.csv         -> payments tied back to CLOSED-WON opportunities

Messiness injected on purpose (so Day 2 cleaning has something real to fix):
  - Inconsistent region spellings/casing ("West", "west", "W.", "WEST ")
  - ~4% missing region values
  - ~2% duplicate opportunity rows
  - A handful of orphan payments (order references an opp_id that doesn't exist)
  - Mixed date string formats
  - A few negative/zero deal values (data-entry errors to catch in QA)

Run:  python3 day1_generate_data.py
Output: ./data/raw/*.csv
"""

import numpy as np
import pandas as pd
from faker import Faker
import random
import os

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
fake = Faker()
Faker.seed(SEED)

OUT_DIR = "data/raw"
os.makedirs(OUT_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# 1. DIMENSIONS: reps, regions, products
# ---------------------------------------------------------------------------
CANONICAL_REGIONS = ["North", "South", "East", "West", "Central"]

# messy variants that will appear in the *fact* data (not here) to simulate
# inconsistent manual entry downstream
REGION_VARIANTS = {
    "North": ["North", "north", "NORTH", "N.", " North"],
    "South": ["South", "south", "SOUTH", "S.", "South "],
    "East":  ["East", "east", "EAST", "E."],
    "West":  ["West", "west", "WEST", "W.", "west "],
    "Central": ["Central", "central", "CENTRAL", "Centrl", "Central "],  # includes a typo
}

N_REPS = 40
reps = pd.DataFrame({
    "rep_id": [f"REP{str(i).zfill(3)}" for i in range(1, N_REPS + 1)],
    "rep_name": [fake.name() for _ in range(N_REPS)],
    "home_region": np.random.choice(CANONICAL_REGIONS, N_REPS),
    "hire_date": [fake.date_between(start_date="-4y", end_date="-30d") for _ in range(N_REPS)],
})

PRODUCT_CATALOG = [
    ("PRD01", "Starter Plan", "Subscription", 29),
    ("PRD02", "Growth Plan", "Subscription", 79),
    ("PRD03", "Enterprise Plan", "Subscription", 249),
    ("PRD04", "Analytics Add-on", "Add-on", 39),
    ("PRD05", "Onboarding Package", "Services", 500),
    ("PRD06", "Premium Support", "Services", 150),
    ("PRD07", "API Access", "Add-on", 59),
    ("PRD08", "Custom Integration", "Services", 1200),
    ("PRD09", "Team Seats (10-pack)", "Subscription", 199),
    ("PRD10", "Data Export Tool", "Add-on", 25),
    ("PRD11", "White-Label Package", "Services", 899),
    ("PRD12", "Compliance Module", "Add-on", 120),
    ("PRD13", "SSO / SAML", "Add-on", 89),
    ("PRD14", "Mobile App License", "Subscription", 49),
    ("PRD15", "Dedicated CSM", "Services", 650),
]
products = pd.DataFrame(PRODUCT_CATALOG, columns=["product_id", "product_name", "category", "unit_price"])

reps.to_csv(f"{OUT_DIR}/reps.csv", index=False)
products.to_csv(f"{OUT_DIR}/products.csv", index=False)

# ---------------------------------------------------------------------------
# 2. LEADS / OPPORTUNITIES (the pipeline)
# ---------------------------------------------------------------------------
N_OPPS = 8000
CHANNELS = ["Outbound", "Inbound", "Referral", "Partner", "Web Signup"]
STAGES = ["Lead", "Qualified", "Proposal", "Closed Won", "Closed Lost"]

# realistic funnel drop-off: fewer records survive to later stages
stage_weights = [0.32, 0.27, 0.18, 0.12, 0.11]

rows = []
for i in range(1, N_OPPS + 1):
    opp_id = f"OPP{str(i).zfill(5)}"
    rep = reps.sample(1).iloc[0]
    product = products.sample(1).iloc[0]
    channel = np.random.choice(CHANNELS, p=[0.30, 0.30, 0.15, 0.15, 0.10])
    stage = np.random.choice(STAGES, p=stage_weights)

    created = fake.date_between(start_date="-14M", end_date="-1d")
    # close_date only makes sense for closed deals
    close_date = None
    if stage in ("Closed Won", "Closed Lost"):
        close_date = fake.date_between(start_date=created, end_date="today")

    deal_value = round(np.random.gamma(shape=2.0, scale=float(product["unit_price"])), 2)
    # inject a few data-entry errors
    if random.random() < 0.005:
        deal_value = -abs(deal_value)  # negative value error
    if random.random() < 0.004:
        deal_value = 0

    # region as messy free text, occasionally missing
    canonical_region = rep["home_region"]
    if random.random() < 0.04:
        region_raw = np.nan
    else:
        region_raw = random.choice(REGION_VARIANTS[canonical_region])

    # mix date formats to force real cleaning work
    def fmt_date(d):
        if d is None:
            return None
        choice = random.random()
        if choice < 0.6:
            return d.strftime("%Y-%m-%d")
        elif choice < 0.85:
            return d.strftime("%m/%d/%Y")
        else:
            return d.strftime("%d-%b-%Y")

    rows.append({
        "opp_id": opp_id,
        "rep_id": rep["rep_id"],
        "product_id": product["product_id"],
        "channel": channel,
        "region_raw": region_raw,
        "stage": stage,
        "deal_value": deal_value,
        "created_date": fmt_date(created),
        "close_date": fmt_date(close_date),
    })

opps = pd.DataFrame(rows)

# inject ~2% duplicate rows (exact dupes -> simulates double CRM sync)
dupe_sample = opps.sample(frac=0.02, random_state=SEED)
opps = pd.concat([opps, dupe_sample], ignore_index=True)

opps.to_csv(f"{OUT_DIR}/leads_opportunities.csv", index=False)

# ---------------------------------------------------------------------------
# 3. ORDERS / PAYMENTS (only for Closed Won opportunities)
# ---------------------------------------------------------------------------
closed_won = opps[opps["stage"] == "Closed Won"].drop_duplicates(subset="opp_id")

payment_rows = []
for i, (_, opp) in enumerate(closed_won.iterrows(), start=1):
    order_id = f"ORD{str(i).zfill(5)}"
    payment_rows.append({
        "order_id": order_id,
        "opp_id": opp["opp_id"],
        "amount": opp["deal_value"],
        "payment_status": np.random.choice(
            ["Paid", "Refunded", "Pending"], p=[0.88, 0.05, 0.07]
        ),
        "payment_date": opp["close_date"],
    })

payments = pd.DataFrame(payment_rows)

# inject a handful of orphan payments (opp_id that doesn't exist) — simulates
# a broken CRM sync, a classic real-world join problem
orphan_rows = payments.sample(min(15, len(payments)), random_state=SEED).copy()
orphan_rows["order_id"] = [f"ORD9{str(i).zfill(4)}" for i in range(len(orphan_rows))]
orphan_rows["opp_id"] = [f"OPP9{str(i).zfill(4)}" for i in range(len(orphan_rows))]  # doesn't exist in opps
payments = pd.concat([payments, orphan_rows], ignore_index=True)

payments.to_csv(f"{OUT_DIR}/orders_payments.csv", index=False)

# ---------------------------------------------------------------------------
print("Done. Files written to", OUT_DIR)
print(f"  reps.csv                 -> {len(reps)} rows")
print(f"  products.csv              -> {len(products)} rows")
print(f"  leads_opportunities.csv   -> {len(opps)} rows")
print(f"  orders_payments.csv       -> {len(payments)} rows")
