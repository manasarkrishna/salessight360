# SalesSight 360 — Data Dictionary (v1, Day 2)

## Star Schema Overview
```
        dim_rep       dim_region      dim_product
            \              |               /
             \             |              /
              fact_opportunities --- fact_payments
             /             |
            /              |
      dim_channel       dim_date
```

## Fact Tables

### fact_opportunities (grain: one row per sales opportunity)
| Column | Type | Description |
|---|---|---|
| opp_id | text (PK) | Unique opportunity identifier |
| rep_id | text (FK -> dim_rep) | Owning sales rep |
| product_id | text (FK -> dim_product) | Product/plan being sold |
| region_id | int (FK -> dim_region) | Standardized region |
| channel_id | int (FK -> dim_channel) | Acquisition channel |
| stage | text | Lead / Qualified / Proposal / Closed Won / Closed Lost |
| deal_value | float | Deal value in USD (sign-corrected) |
| deal_value_flag | text | 'OK' or 'REVIEW' — flags deals that had a zero/negative raw value |
| created_date_id | int (FK -> dim_date) | Date opportunity was created |
| close_date_id | int (FK -> dim_date) | Date opportunity was closed (null if still open) |

### fact_payments (grain: one row per payment/order)
| Column | Type | Description |
|---|---|---|
| order_id | text (PK) | Unique order identifier |
| opp_id | text (FK -> fact_opportunities) | Opportunity this payment fulfills |
| amount | float | Payment amount in USD |
| payment_status | text | Paid / Refunded / Pending |
| payment_date_id | int (FK -> dim_date) | Payment date |

## Dimension Tables
- **dim_rep**: rep_id, rep_name, region_id, hire_date
- **dim_region**: region_id, region_name (North/South/East/West/Central)
- **dim_product**: product_id, product_name, category, unit_price
- **dim_channel**: channel_id, channel_name (Outbound/Inbound/Referral/Partner/Web Signup)
- **dim_date**: date_id (YYYYMMDD), year, month, month_name, quarter

## Known Data Quality Notes (from Day 2 QA log)
- 160 exact-duplicate opportunity rows removed (simulated double CRM sync).
- 332 opportunities had missing region — backfilled from the owning rep's home region (documented business rule; revisit if a rep changes territory mid-deal).
- 46 negative and 30 zero deal values found — sign-corrected and flagged `REVIEW` rather than silently dropped, so they're auditable.
- 15 orphan payments referenced an opp_id with no matching opportunity — excluded from fact_payments, retained in `orphan_payments.csv` for audit.
- Dates arrived in 3 different formats (`YYYY-MM-DD`, `MM/DD/YYYY`, `DD-Mon-YYYY`) — all normalized to ISO 8601.
