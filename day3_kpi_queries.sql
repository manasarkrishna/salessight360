-- =============================================================================
-- SalesSight 360 — Day 3: Core KPI Layer (SQL)
-- Target: Postgres (run via pgAdmin4 Query Tool, or via day3_run_kpis.py)
-- =============================================================================
-- Verified against Postgres 16. Two dialect gotchas already fixed here vs.
-- an earlier SQLite draft, worth knowing if you ever port SQL between engines:
--   1. Postgres enforces strict GROUP BY — every non-aggregated SELECT column
--      must appear in GROUP BY. SQLite is lenient about this.
--   2. Postgres's HAVING can't reference a SELECT-list alias (e.g. HAVING
--      deals_closed > 0) — you must repeat the full aggregate expression.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1. REVENUE BY REGION / MONTH  (only counts actually PAID payments — a real
--    revenue number should never include Pending/Refunded)
-- -----------------------------------------------------------------------------
SELECT
    r.region_name,
    d.year,
    d.month,
    d.month_name,
    ROUND(SUM(p.amount), 2) AS revenue
FROM fact_payments p
JOIN fact_opportunities o ON p.opp_id = o.opp_id
JOIN dim_region r ON o.region_id = r.region_id
JOIN dim_date d ON p.payment_date_id = d.date_id
WHERE p.payment_status = 'Paid'
GROUP BY r.region_name, d.year, d.month, d.month_name
ORDER BY r.region_name, d.year, d.month;


-- -----------------------------------------------------------------------------
-- 2. PIPELINE VALUE BY REGION  (open deals only — not yet Closed Won/Lost)
-- -----------------------------------------------------------------------------
SELECT
    r.region_name,
    COUNT(*)                       AS open_deal_count,
    ROUND(SUM(o.deal_value), 2)    AS pipeline_value
FROM fact_opportunities o
JOIN dim_region r ON o.region_id = r.region_id
WHERE o.stage NOT IN ('Closed Won', 'Closed Lost')
GROUP BY r.region_name
ORDER BY pipeline_value DESC;


-- -----------------------------------------------------------------------------
-- 3. WIN RATE BY REP / REGION / CHANNEL
--    win_rate = Closed Won / (Closed Won + Closed Lost)
-- -----------------------------------------------------------------------------

-- 3a. By rep
SELECT
    rep.rep_name,
    r.region_name,
    SUM(CASE WHEN o.stage = 'Closed Won' THEN 1 ELSE 0 END)                       AS deals_won,
    SUM(CASE WHEN o.stage IN ('Closed Won','Closed Lost') THEN 1 ELSE 0 END)      AS deals_closed,
    ROUND(
        1.0 * SUM(CASE WHEN o.stage = 'Closed Won' THEN 1 ELSE 0 END)
        / NULLIF(SUM(CASE WHEN o.stage IN ('Closed Won','Closed Lost') THEN 1 ELSE 0 END), 0),
    3) AS win_rate
FROM fact_opportunities o
JOIN dim_rep rep ON o.rep_id = rep.rep_id
JOIN dim_region r ON rep.region_id = r.region_id
GROUP BY rep.rep_name, r.region_name
HAVING SUM(CASE WHEN o.stage IN ('Closed Won','Closed Lost') THEN 1 ELSE 0 END) > 0
ORDER BY win_rate DESC;

-- 3b. By channel (which acquisition channel actually converts?)
SELECT
    c.channel_name,
    SUM(CASE WHEN o.stage = 'Closed Won' THEN 1 ELSE 0 END)                       AS deals_won,
    SUM(CASE WHEN o.stage IN ('Closed Won','Closed Lost') THEN 1 ELSE 0 END)      AS deals_closed,
    ROUND(
        1.0 * SUM(CASE WHEN o.stage = 'Closed Won' THEN 1 ELSE 0 END)
        / NULLIF(SUM(CASE WHEN o.stage IN ('Closed Won','Closed Lost') THEN 1 ELSE 0 END), 0),
    3) AS win_rate
FROM fact_opportunities o
JOIN dim_channel c ON o.channel_id = c.channel_id
GROUP BY c.channel_name
ORDER BY win_rate DESC;


-- -----------------------------------------------------------------------------
-- 4. AVERAGE DEAL SIZE BY REGION / CHANNEL / MONTH  (Closed Won only —
--    open-pipeline deal sizes are speculative, closed ones are real)
-- -----------------------------------------------------------------------------
SELECT
    r.region_name,
    c.channel_name,
    d.year,
    d.month,
    ROUND(AVG(o.deal_value), 2) AS avg_deal_size,
    COUNT(*)                    AS deals_won
FROM fact_opportunities o
JOIN dim_region r ON o.region_id = r.region_id
JOIN dim_channel c ON o.channel_id = c.channel_id
JOIN dim_date d ON o.close_date_id = d.date_id
WHERE o.stage = 'Closed Won'
GROUP BY r.region_name, c.channel_name, d.year, d.month
ORDER BY r.region_name, d.year, d.month;


-- -----------------------------------------------------------------------------
-- 5. WINDOW FUNCTIONS — the section interviewers actually probe on
-- -----------------------------------------------------------------------------

-- 5a. Running total of monthly revenue (company-wide)
WITH monthly_revenue AS (
    SELECT d.year, d.month, ROUND(SUM(p.amount), 2) AS revenue
    FROM fact_payments p
    JOIN dim_date d ON p.payment_date_id = d.date_id
    WHERE p.payment_status = 'Paid'
    GROUP BY d.year, d.month
)
SELECT
    year, month, revenue,
    ROUND(SUM(revenue) OVER (ORDER BY year, month), 2) AS running_total_revenue
FROM monthly_revenue
ORDER BY year, month;

-- 5b. Rank reps by total closed-won revenue (within their region)
WITH rep_revenue AS (
    SELECT
        rep.rep_id, rep.rep_name, r.region_name,
        ROUND(SUM(o.deal_value), 2) AS total_won_revenue
    FROM fact_opportunities o
    JOIN dim_rep rep ON o.rep_id = rep.rep_id
    JOIN dim_region r ON rep.region_id = r.region_id
    WHERE o.stage = 'Closed Won'
    GROUP BY rep.rep_id, rep.rep_name, r.region_name
)
SELECT
    region_name, rep_name, total_won_revenue,
    RANK() OVER (PARTITION BY region_name ORDER BY total_won_revenue DESC) AS rank_in_region
FROM rep_revenue
ORDER BY region_name, rank_in_region;

-- 5c. Month-over-month % change in revenue, by region
WITH monthly_region_revenue AS (
    SELECT r.region_name, d.year, d.month, ROUND(SUM(p.amount), 2) AS revenue
    FROM fact_payments p
    JOIN fact_opportunities o ON p.opp_id = o.opp_id
    JOIN dim_region r ON o.region_id = r.region_id
    JOIN dim_date d ON p.payment_date_id = d.date_id
    WHERE p.payment_status = 'Paid'
    GROUP BY r.region_name, d.year, d.month
)
SELECT
    region_name, year, month, revenue,
    LAG(revenue) OVER (PARTITION BY region_name ORDER BY year, month) AS prev_month_revenue,
    ROUND(
        100.0 * (revenue - LAG(revenue) OVER (PARTITION BY region_name ORDER BY year, month))
        / NULLIF(LAG(revenue) OVER (PARTITION BY region_name ORDER BY year, month), 0),
    1) AS mom_pct_change
FROM monthly_region_revenue
ORDER BY region_name, year, month;
