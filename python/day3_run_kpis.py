"""
SalesSight 360 — Day 3 runner (POSTGRES VERSION)
Executes each named query block from day3_kpi_queries.sql against the
Postgres star schema and saves results to data/kpis/*.csv — these CSVs
are what you screenshot/chart in your write-up and Power BI/Tableau import.

BEFORE RUNNING: edit PG_CONFIG below to match your local pgAdmin4 setup
(same credentials used in day2_clean_and_model_postgres.py).

Run:  python3 day3_run_kpis.py
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

QUERIES = {

"revenue_by_region_month": """
    SELECT r.region_name, d.year, d.month, d.month_name,
           ROUND(SUM(p.amount), 2) AS revenue
    FROM fact_payments p
    JOIN fact_opportunities o ON p.opp_id = o.opp_id
    JOIN dim_region r ON o.region_id = r.region_id
    JOIN dim_date d ON p.payment_date_id = d.date_id
    WHERE p.payment_status = 'Paid'
    GROUP BY r.region_name, d.year, d.month, d.month_name
    ORDER BY r.region_name, d.year, d.month;
""",

"pipeline_value_by_region": """
    SELECT r.region_name, COUNT(*) AS open_deal_count,
           ROUND(SUM(o.deal_value), 2) AS pipeline_value
    FROM fact_opportunities o
    JOIN dim_region r ON o.region_id = r.region_id
    WHERE o.stage NOT IN ('Closed Won', 'Closed Lost')
    GROUP BY r.region_name
    ORDER BY pipeline_value DESC;
""",

"win_rate_by_rep": """
    SELECT rep.rep_name, r.region_name,
           SUM(CASE WHEN o.stage='Closed Won' THEN 1 ELSE 0 END) AS deals_won,
           SUM(CASE WHEN o.stage IN ('Closed Won','Closed Lost') THEN 1 ELSE 0 END) AS deals_closed,
           ROUND(1.0*SUM(CASE WHEN o.stage='Closed Won' THEN 1 ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN o.stage IN ('Closed Won','Closed Lost') THEN 1 ELSE 0 END),0), 3) AS win_rate
    FROM fact_opportunities o
    JOIN dim_rep rep ON o.rep_id = rep.rep_id
    JOIN dim_region r ON rep.region_id = r.region_id
    GROUP BY rep.rep_name, r.region_name
    HAVING SUM(CASE WHEN o.stage IN ('Closed Won','Closed Lost') THEN 1 ELSE 0 END) > 0
    ORDER BY win_rate DESC;
""",

"win_rate_by_channel": """
    SELECT c.channel_name,
           SUM(CASE WHEN o.stage='Closed Won' THEN 1 ELSE 0 END) AS deals_won,
           SUM(CASE WHEN o.stage IN ('Closed Won','Closed Lost') THEN 1 ELSE 0 END) AS deals_closed,
           ROUND(1.0*SUM(CASE WHEN o.stage='Closed Won' THEN 1 ELSE 0 END)
                 / NULLIF(SUM(CASE WHEN o.stage IN ('Closed Won','Closed Lost') THEN 1 ELSE 0 END),0), 3) AS win_rate
    FROM fact_opportunities o
    JOIN dim_channel c ON o.channel_id = c.channel_id
    GROUP BY c.channel_name
    ORDER BY win_rate DESC;
""",

"avg_deal_size": """
    SELECT r.region_name, c.channel_name, d.year, d.month,
           ROUND(AVG(o.deal_value), 2) AS avg_deal_size, COUNT(*) AS deals_won
    FROM fact_opportunities o
    JOIN dim_region r ON o.region_id = r.region_id
    JOIN dim_channel c ON o.channel_id = c.channel_id
    JOIN dim_date d ON o.close_date_id = d.date_id
    WHERE o.stage = 'Closed Won'
    GROUP BY r.region_name, c.channel_name, d.year, d.month
    ORDER BY r.region_name, d.year, d.month;
""",

"running_total_revenue": """
    WITH monthly_revenue AS (
        SELECT d.year, d.month, ROUND(SUM(p.amount), 2) AS revenue
        FROM fact_payments p
        JOIN dim_date d ON p.payment_date_id = d.date_id
        WHERE p.payment_status = 'Paid'
        GROUP BY d.year, d.month
    )
    SELECT year, month, revenue,
           ROUND(SUM(revenue) OVER (ORDER BY year, month), 2) AS running_total_revenue
    FROM monthly_revenue
    ORDER BY year, month;
""",

"rep_rank_by_region": """
    WITH rep_revenue AS (
        SELECT rep.rep_id, rep.rep_name, r.region_name,
               ROUND(SUM(o.deal_value), 2) AS total_won_revenue
        FROM fact_opportunities o
        JOIN dim_rep rep ON o.rep_id = rep.rep_id
        JOIN dim_region r ON rep.region_id = r.region_id
        WHERE o.stage = 'Closed Won'
        GROUP BY rep.rep_id, rep.rep_name, r.region_name
    )
    SELECT region_name, rep_name, total_won_revenue,
           RANK() OVER (PARTITION BY region_name ORDER BY total_won_revenue DESC) AS rank_in_region
    FROM rep_revenue
    ORDER BY region_name, rank_in_region;
""",

"mom_pct_change_by_region": """
    WITH monthly_region_revenue AS (
        SELECT r.region_name, d.year, d.month, ROUND(SUM(p.amount), 2) AS revenue
        FROM fact_payments p
        JOIN fact_opportunities o ON p.opp_id = o.opp_id
        JOIN dim_region r ON o.region_id = r.region_id
        JOIN dim_date d ON p.payment_date_id = d.date_id
        WHERE p.payment_status = 'Paid'
        GROUP BY r.region_name, d.year, d.month
    )
    SELECT region_name, year, month, revenue,
           LAG(revenue) OVER (PARTITION BY region_name ORDER BY year, month) AS prev_month_revenue,
           ROUND(100.0*(revenue - LAG(revenue) OVER (PARTITION BY region_name ORDER BY year, month))
                 / NULLIF(LAG(revenue) OVER (PARTITION BY region_name ORDER BY year, month), 0), 1) AS mom_pct_change
    FROM monthly_region_revenue
    ORDER BY region_name, year, month;
"""
}

for name, sql in QUERIES.items():
    df = pd.read_sql_query(sql, engine)
    df.to_csv(f"{OUT_DIR}/{name}.csv", index=False)
    print(f"{name:30s} -> {len(df)} rows -> {OUT_DIR}/{name}.csv")

engine.dispose()
print("\nDay 3 complete. All KPI outputs saved to", OUT_DIR)
