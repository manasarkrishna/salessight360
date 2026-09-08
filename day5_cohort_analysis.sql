-- =============================================================================
-- SalesSight 360 — Day 5: Cohort Analysis (SQL)
-- Target: Postgres. Run via pgAdmin4 Query Tool or day5_cohort_analysis.py
-- =============================================================================
-- Cohort = the calendar month an opportunity was CREATED (acquisition month).
-- "Age" = how many months after creation a deal closed as Closed Won.
-- The question this answers: "of the leads we brought in during month X,
-- what % have converted by month 0, month 1, month 2... after creation?"


-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. COHORT SIZES — how many opportunities were created in each acquisition month
-- -----------------------------------------------------------------------------
SELECT
    dc.year * 12 + dc.month AS cohort_index,   -- a sortable single integer for year+month
    dc.year,
    dc.month,
    COUNT(*) AS cohort_size
FROM fact_opportunities o
JOIN dim_date dc ON o.created_date_id = dc.date_id
GROUP BY dc.year, dc.month
ORDER BY cohort_index;


-- -----------------------------------------------------------------------------
-- 2. WINS BY COHORT + AGE, with a cumulative running total via window function
--    (age_months = months between creation and close, for Closed Won deals only)
-- -----------------------------------------------------------------------------
WITH cohort_base AS (
    SELECT
        o.opp_id,
        dc.year * 12 + dc.month AS cohort_index,
        dw.year * 12 + dw.month AS win_index
    FROM fact_opportunities o
    JOIN dim_date dc ON o.created_date_id = dc.date_id
    JOIN dim_date dw ON o.close_date_id = dw.date_id
    WHERE o.stage = 'Closed Won'
),
win_by_age AS (
    SELECT
        cohort_index,
        (win_index - cohort_index) AS age_months,
        COUNT(*) AS wins
    FROM cohort_base
    GROUP BY cohort_index, age_months
)
SELECT
    cohort_index,
    age_months,
    wins,
    SUM(wins) OVER (PARTITION BY cohort_index ORDER BY age_months) AS cumulative_wins
FROM win_by_age
ORDER BY cohort_index, age_months;
