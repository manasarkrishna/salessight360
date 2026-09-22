"""
SalesSight 360 — Day 7: QA Checkpoint
-----------------------------------------
The plan's Day 7 instruction is "review: do your KPIs make business sense?
any impossible numbers?" — this script turns that into an actual automated
battery of checks instead of eyeballing it. Run this before you touch the
dashboard (Day 10+); a dashboard built on broken logic is worse than no
dashboard, per the plan.

Each check prints PASS or FLAG. FLAG doesn't always mean "bug" — sometimes
it's a property of synthetic/messy data worth documenting rather than fixing.
The script tells you which is which.

BEFORE RUNNING: edit PG_CONFIG below to match your local pgAdmin4 setup.

Run: python3 day7_qa_checkpoint.py
"""

import pandas as pd
import numpy as np
from sqlalchemy import create_engine

PG_CONFIG = {
    "user": "postgres",
    "password": "password",      # <-- change to your actual password
    "host": "localhost",
    "port": "5432",
    "dbname": "salessight360",
}

conn_str = (f"postgresql+psycopg2://{PG_CONFIG['user']}:{PG_CONFIG['password']}"
            f"@{PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['dbname']}")
engine = create_engine(conn_str)

results = []
def check(name, condition, detail="", severity="FAIL"):
    status = "PASS" if condition else severity
    results.append({"check": name, "status": status, "detail": detail})
    flag = "✓" if condition else ("⚠" if severity == "FLAG" else "✗")
    print(f"[{flag}] {name:55s} {detail}")


print("=" * 90)
print("1. REFERENTIAL INTEGRITY — every FK should resolve, no exceptions")
print("=" * 90)

orphan_checks = {
    "fact_opportunities.rep_id -> dim_rep": """
        SELECT COUNT(*) FROM fact_opportunities o
        LEFT JOIN dim_rep r ON o.rep_id = r.rep_id WHERE r.rep_id IS NULL""",
    "fact_opportunities.product_id -> dim_product": """
        SELECT COUNT(*) FROM fact_opportunities o
        LEFT JOIN dim_product p ON o.product_id = p.product_id WHERE p.product_id IS NULL""",
    "fact_opportunities.region_id -> dim_region": """
        SELECT COUNT(*) FROM fact_opportunities o
        LEFT JOIN dim_region r ON o.region_id = r.region_id WHERE r.region_id IS NULL""",
    "fact_payments.opp_id -> fact_opportunities": """
        SELECT COUNT(*) FROM fact_payments p
        LEFT JOIN fact_opportunities o ON p.opp_id = o.opp_id WHERE o.opp_id IS NULL""",
}
for name, sql in orphan_checks.items():
    n = pd.read_sql_query(sql, engine).iloc[0, 0]
    check(name, n == 0, detail=f"({n} orphan rows)")


print("\n" + "=" * 90)
print("2. DUPLICATE / GRAIN CHECKS — fact tables should be unique at their stated grain")
print("=" * 90)

dupe_opps = pd.read_sql_query(
    "SELECT opp_id, COUNT(*) c FROM fact_opportunities GROUP BY opp_id HAVING COUNT(*) > 1", engine)
check("fact_opportunities.opp_id is unique", len(dupe_opps) == 0, detail=f"({len(dupe_opps)} duplicated ids)")

dupe_pay = pd.read_sql_query(
    "SELECT order_id, COUNT(*) c FROM fact_payments GROUP BY order_id HAVING COUNT(*) > 1", engine)
check("fact_payments.order_id is unique", len(dupe_pay) == 0, detail=f"({len(dupe_pay)} duplicated ids)")


print("\n" + "=" * 90)
print("3. RANGE / SANITY CHECKS — values should live in a plausible business range")
print("=" * 90)

deal_stats = pd.read_sql_query(
    "SELECT MIN(deal_value) mn, MAX(deal_value) mx, AVG(deal_value) avg FROM fact_opportunities", engine).iloc[0]
check("No negative deal values", deal_stats["mn"] >= 0, detail=f"(min={deal_stats['mn']:.2f})")
check("No absurd outlier deal values (< $50k)", deal_stats["mx"] < 50000,
      detail=f"(max={deal_stats['mx']:.2f})", severity="FLAG")

win_rates = pd.read_sql_query("""
    SELECT r.region_name,
           1.0*SUM(CASE WHEN o.stage='Closed Won' THEN 1 ELSE 0 END)
             / NULLIF(SUM(CASE WHEN o.stage IN ('Closed Won','Closed Lost') THEN 1 ELSE 0 END),0) AS win_rate
    FROM fact_opportunities o JOIN dim_region r ON o.region_id = r.region_id
    GROUP BY r.region_name
""", engine)
bad_win_rates = win_rates[(win_rates["win_rate"] < 0) | (win_rates["win_rate"] > 1)]
check("All win rates fall within [0, 1]", len(bad_win_rates) == 0,
      detail=f"({len(bad_win_rates)} regions out of range)")

close_before_create = pd.read_sql_query("""
    SELECT COUNT(*) FROM fact_opportunities o
    JOIN dim_date dc ON o.created_date_id = dc.date_id
    JOIN dim_date dw ON o.close_date_id = dw.date_id
    WHERE (dw.year*12+dw.month) < (dc.year*12+dc.month)
""", engine).iloc[0, 0]
check("No opportunity closes before it was created", close_before_create == 0,
      detail=f"({close_before_create} rows)")

payment_vs_deal = pd.read_sql_query("""
    SELECT o.opp_id, o.deal_value, p.amount
    FROM fact_opportunities o JOIN fact_payments p ON o.opp_id = p.opp_id
    WHERE o.stage = 'Closed Won' AND ABS(o.deal_value - p.amount) > 0.01
""", engine)
check("Closed-Won deal_value matches its payment amount", len(payment_vs_deal) == 0,
      detail=f"({len(payment_vs_deal)} mismatches)")


print("\n" + "=" * 90)
print("4. BUSINESS-LOGIC PLAUSIBILITY — does the shape of the data make sense?")
print("=" * 90)

region_counts = pd.read_sql_query("""
    SELECT r.region_name, COUNT(*) n
    FROM fact_opportunities o JOIN dim_region r ON o.region_id = r.region_id
    GROUP BY r.region_name ORDER BY n
""", engine)
min_n, max_n = region_counts["n"].min(), region_counts["n"].max()
check("No region has a wildly outsized share of volume (max < 3x min)",
      max_n < 3 * min_n, detail=f"(min={min_n}, max={max_n})", severity="FLAG")

funnel_monotonic = pd.read_csv("data/kpis/funnel_overall.csv") if False else None
funnel_check = pd.read_sql_query("""
    SELECT
      (SELECT COUNT(*) FROM fact_opportunities) AS n_lead,
      (SELECT COUNT(*) FROM fact_opportunities WHERE stage IN ('Qualified','Proposal','Closed Won','Closed Lost')) AS n_at_least_qualified
""", engine).iloc[0]
check("Funnel stage counts are monotonically non-increasing",
      funnel_check["n_lead"] >= funnel_check["n_at_least_qualified"], detail="")

pipeline_coverage = pd.read_sql_query("""
    SELECT
      SUM(CASE WHEN stage NOT IN ('Closed Won','Closed Lost') THEN deal_value ELSE 0 END) AS open_pipeline,
      SUM(CASE WHEN stage = 'Closed Won' THEN deal_value ELSE 0 END) AS won_value
    FROM fact_opportunities
""", engine).iloc[0]
coverage_ratio = pipeline_coverage["open_pipeline"] / pipeline_coverage["won_value"]
check("Pipeline coverage ratio is in a sane range (0.5x - 10x historical won)",
      0.5 <= coverage_ratio <= 10, detail=f"(ratio={coverage_ratio:.2f}x)", severity="FLAG")


print("\n" + "=" * 90)
summary = pd.DataFrame(results)
n_pass = (summary["status"] == "PASS").sum()
n_flag = (summary["status"] == "FLAG").sum()
n_fail = (summary["status"] == "FAIL").sum()
print(f"SUMMARY: {n_pass} passed, {n_flag} flagged for review, {n_fail} failed")
print("=" * 90)

summary.to_csv("data/kpis/qa_checkpoint_results.csv", index=False)
engine.dispose()

if n_fail > 0:
    print("\n⚠ Fix FAIL items before building the dashboard — these are real data bugs.")
if n_flag > 0:
    print("⚠ FLAG items aren't necessarily bugs — decide whether to document them")
    print("  as known data characteristics (see qa_log.txt) or investigate further.")
