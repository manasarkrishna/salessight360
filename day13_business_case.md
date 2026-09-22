# SalesSight 360 — Business Case
*What decisions can leadership make from this dashboard?*

## The Problem
Sales leadership currently reports pipeline and revenue using raw, unadjusted numbers — every open deal counted at full value, every "Closed Won" deal treated as collected revenue. This project shows both assumptions are wrong, by how much, and what a corrected view enables.

## Headline Numbers (verified against the underlying data)
- **$419,995** in actual paid revenue across the analyzed period (929 closed-won deals)
- **51.8%** blended win rate (1,795 closed opportunities)
- **$518.34** average deal size
- **$3,576,802** in naive open pipeline — vs. a probability-weighted forecast that is **71–74% lower**, region by region

## Three Decisions This Dashboard Enables

**1. Stop reporting naive pipeline as forecast.**
Every region's raw pipeline overstates realistic expected revenue by roughly three-quarters. Leadership planning off the raw number is planning against a number that will not materialize. The weighted forecast (Day 8) should replace raw pipeline in any forward-looking report.

**2. Reallocate spend toward Web Signup.**
Win-rate analysis shows Web Signup converts at a noticeably higher rate than Outbound and Referral, despite receiving the smallest share of lead volume and rep attention. This is a concrete, numbers-backed case for shifting acquisition budget toward the channel that already converts best, rather than the channel that generates the most raw leads.

**3. Target coaching, not blanket pipeline-generation pressure.**
Rather than telling every rep to "build more pipeline," the bottom-quartile coverage analysis (Day 9) identifies exactly which reps have a real, relative shortfall (e.g. Gina Moore at 3.87x weighted coverage vs. a 13.2x team median) — a specific, actionable coaching list instead of a generic all-hands directive.

## What Would Change This Recommendation
- Real quota/target data (this project approximates targets as 110% of trailing 3-month run-rate, documented in the KPI dictionary, since no quota table exists in the source export)
- An `expected_close_date` field on open deals, which would allow pipeline to be properly scoped to a selling period instead of compared against unbounded historical accumulation
- A longer observation window — several of the newest lead cohorts are still right-censored and haven't had time to fully convert

## Data Caveat
This project uses synthetic data generated to resemble a real, messy CRM export (intentional duplicates, missing values, and mixed date formats were injected and then cleaned as part of the pipeline). The **analytical methodology — win-rate calculation, weighted forecasting, cohort right-censoring awareness, and coverage-ratio logic — is the deliverable**, and is built to apply directly to a real CRM export with the same schema.
