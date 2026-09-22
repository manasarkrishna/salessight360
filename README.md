# SalesSight 360
**Multi-Channel Revenue Analytics Platform** — an end-to-end sales analytics project covering data modeling, SQL, funnel analytics, forecasting, and executive dashboarding.

## Live Dashboard
🔗 [View on Tableau Public](https://public.tableau.com/app/profile/manasa.r.krishna/viz/SalesSight360SalesForecastAnalytics/ExecutiveSummary?publish=yes&showOnboarding=true) 

![Dashboard Screenshot](![Executive Summary](image.png)) 

## The Problem
Sales leadership was reporting pipeline and revenue using raw, unadjusted numbers — every open deal counted at full value, every "Closed Won" deal treated as collected cash. This project builds a cleaned, modeled analytics layer that corrects both assumptions and quantifies exactly how wrong they were.

## Key Insights
- **Naive pipeline overstates realistic forecast by 71–74%** across every region — a probability-weighted forecast model (stage-based win rates: Lead 10%, Qualified 30%, Proposal 60%) replaces it with a defensible number.
- **Web Signup has the highest win rate of any channel**, despite receiving the least lead volume and rep attention — a concrete, numbers-backed case for reallocating acquisition spend.
- **$419,995** in verified paid revenue, **51.8%** blended win rate, **$518.34** average deal size across 929 closed-won deals.
- Caught and fixed a **real pipeline bug** during Day 7 QA: a sign-correction applied to `deal_value` wasn't propagated to `fact_payments.amount`, silently skewing revenue by a small amount across every downstream KPI until traced back to its Day 1/Day 2 root cause.

## Tech Stack
`Python (pandas, Faker, SQLAlchemy)` · `PostgreSQL` · `SQL (window functions: RANK, LAG, SUM OVER)` · `Tableau Public` · `Jupyter`

## Methodology Notes
- **Synthetic data, deliberately messy**: generated with realistic CRM problems (duplicate rows, inconsistent region spellings, missing values, mixed date formats, orphan payment records) and cleaned with a documented, auditable QA log — not hand-picked clean data.
- **Cohort analysis accounts for right-censoring**: recent lead cohorts haven't had time to fully convert, so they're explicitly excluded from headline cohort comparisons rather than silently misread as underperforming.
- **Pipeline coverage methodology was revised mid-build**: the standard "3x raw pipeline" industry heuristic returned 0 at-risk reps out of 40 — not because the business was healthy, but because raw pipeline is an unbounded accumulated stock being compared against a single month's target. Switched to a probability-weighted, peer-relative coverage model instead. (Full reasoning documented in `day9_variance_alerts.py`.)
- **Forecast accuracy backtest** uses a documented approximation (last-known-stage before close) since the source data has no point-in-time snapshots — stated explicitly rather than glossed over. MAPE: 22.6%.

## Repo Structure
```
├── day1_generate_data.py              # Synthetic CRM data generator (messy, on purpose)
├── day2_clean_and_model.py            # Cleaning + star schema (SQLite version)
├── day2_clean_and_model_postgres.py   # Same, loading into Postgres with real PK/FK constraints
├── day3_kpi_queries.sql               # Revenue, pipeline, win rate, window functions
├── day3_run_kpis.py                   # Runner + CSV export
├── day4_funnel_analysis.py            # Funnel + reconstructed stage-progression model
├── day4_funnel_query.sql              # Pure-SQL funnel version
├── day5_cohort_analysis.sql/.py       # Cohort sizing + conversion matrix
├── day6_python_layer.py / .ipynb      # Pandas-native rebuild + 3 charts (executed notebook)
├── day7_qa_checkpoint.py              # 14 automated data-sanity checks
├── day8_forecasting.py                # Weighted pipeline forecast + accuracy backtest
├── day9_variance_alerts.py            # Pipeline coverage + at-risk alerting
├── day10_tableau_prep.py              # Flat CSV exports for Tableau Public
├── day13_kpi_dictionary.md            # Every metric, formula, and business meaning
├── day13_business_case.md             # Decisions this dashboard enables
├── data_dictionary.md                 # Star schema table/column reference
└── qa_log.txt                         # Every cleaning fix, with row counts
```

## How to Run
```bash
pip install pandas numpy faker sqlalchemy psycopg2-binary matplotlib seaborn
# Create a Postgres database named salessight360, then edit PG_CONFIG at the
# top of each script with your credentials.
python3 day1_generate_data.py
python3 day2_clean_and_model_postgres.py
python3 day3_run_kpis.py
python3 day4_funnel_analysis.py
python3 day5_cohort_analysis.py
python3 day6_python_layer.py
python3 day7_qa_checkpoint.py   # should print 14 passed, 0 failed
python3 day8_forecasting.py
python3 day9_variance_alerts.py
python3 day10_tableau_prep.py   # produces CSVs for Tableau Public import
```

## Author
*[Manasa R Krishna]* — [GitHub](github.com/manasarkrishna)
