"""
SalesSight 360 — Day 5: Cohort Analysis runner
-------------------------------------------------
Runs the two SQL queries from day5_cohort_analysis.sql, then pivots them
in pandas into a cohort x age conversion-rate matrix — the classic
"heatmap" shape (rows = acquisition month, columns = months since creation,
values = % of that cohort converted by that age). Day 6 turns this into
an actual heatmap chart.

BEFORE RUNNING: edit PG_CONFIG below to match your local pgAdmin4 setup.

Outputs:
  data/kpis/cohort_sizes.csv
  data/kpis/cohort_wins_by_age.csv
  data/kpis/cohort_conversion_matrix.csv      <- raw cumulative win counts
  data/kpis/cohort_conversion_pct_matrix.csv  <- % of cohort converted (the headline output)

Run: python3 day5_cohort_analysis.py
"""

import pandas as pd
import os
from sqlalchemy import create_engine

PG_CONFIG = {
    "user": "postgres",
    "password": "postman123",      # <-- change to your actual password
    "host": "localhost",
    "port": "5432",
    "dbname": "salessight360",
}

OUT_DIR = "data/kpis"
os.makedirs(OUT_DIR, exist_ok=True)

conn_str = (f"postgresql+psycopg2://{PG_CONFIG['user']}:{PG_CONFIG['password']}"
            f"@{PG_CONFIG['host']}:{PG_CONFIG['port']}/{PG_CONFIG['dbname']}")
engine = create_engine(conn_str)

# ---------------------------------------------------------------------------
# 1. Cohort sizes
# ---------------------------------------------------------------------------
cohort_sizes = pd.read_sql_query("""
    SELECT dc.year * 12 + dc.month AS cohort_index, dc.year, dc.month,
           COUNT(*) AS cohort_size
    FROM fact_opportunities o
    JOIN dim_date dc ON o.created_date_id = dc.date_id
    GROUP BY dc.year, dc.month
    ORDER BY cohort_index;
""", engine)
cohort_sizes.to_csv(f"{OUT_DIR}/cohort_sizes.csv", index=False)

# ---------------------------------------------------------------------------
# 2. Wins by cohort + age, with cumulative running total
# ---------------------------------------------------------------------------
wins_by_age = pd.read_sql_query("""
    WITH cohort_base AS (
        SELECT o.opp_id,
               dc.year * 12 + dc.month AS cohort_index,
               dw.year * 12 + dw.month AS win_index
        FROM fact_opportunities o
        JOIN dim_date dc ON o.created_date_id = dc.date_id
        JOIN dim_date dw ON o.close_date_id = dw.date_id
        WHERE o.stage = 'Closed Won'
    ),
    win_by_age AS (
        SELECT cohort_index, (win_index - cohort_index) AS age_months, COUNT(*) AS wins
        FROM cohort_base
        GROUP BY cohort_index, age_months
    )
    SELECT cohort_index, age_months, wins,
           SUM(wins) OVER (PARTITION BY cohort_index ORDER BY age_months) AS cumulative_wins
    FROM win_by_age
    ORDER BY cohort_index, age_months;
""", engine)
wins_by_age.to_csv(f"{OUT_DIR}/cohort_wins_by_age.csv", index=False)

# ---------------------------------------------------------------------------
# 3. Pivot into cohort x age matrices (this is the "genuinely differentiating"
#    deliverable the plan calls out)
# ---------------------------------------------------------------------------
# label cohorts as "2025-07" style strings for a readable matrix
cohort_label_map = {
    row.cohort_index: f"{int(row.year)}-{int(row.month):02d}"
    for row in cohort_sizes.itertuples()
}
wins_by_age["cohort_label"] = wins_by_age["cohort_index"].map(cohort_label_map)

matrix = wins_by_age.pivot_table(
    index="cohort_label", columns="age_months", values="cumulative_wins", fill_value=0
)
# forward-fill across ages within a row: once a cohort hits N wins, it never drops (cumulative)
matrix = matrix.cummax(axis=1)
matrix.to_csv(f"{OUT_DIR}/cohort_conversion_matrix.csv")

# convert to % of cohort size for the headline "conversion rate over time" view
size_map = {f"{int(r.year)}-{int(r.month):02d}": r.cohort_size for r in cohort_sizes.itertuples()}
pct_matrix = matrix.div(pd.Series(size_map), axis=0) * 100
pct_matrix = pct_matrix.round(1)
pct_matrix.to_csv(f"{OUT_DIR}/cohort_conversion_pct_matrix.csv")

engine.dispose()

print("Cohort sizes (first 5 months):")
print(cohort_sizes.head().to_string(index=False))
print("\nCohort conversion %% matrix (first 6 cohorts, first 6 ages):")
print(pct_matrix.iloc[:6, :6].to_string())
print("\nDay 5 complete. Outputs saved to", OUT_DIR)
