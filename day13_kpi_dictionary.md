# SalesSight 360 — KPI Dictionary

*Every metric in the dashboard, what it means, and why leadership should care.*

| KPI | Formula | Why It Matters |
|---|---|---|
| **Revenue** | `SUM(amount)` from `fact_payments` where `payment_status = 'Paid'` | The only number that represents cash actually collected — not deals marked "won" that haven't been paid yet. Confusing this with `deal_value` overstates revenue by 5–18% depending on region (see Known Issue below). |
| **Win Rate** | `Closed Won ÷ (Closed Won + Closed Lost)` | Measures deal-execution quality independent of volume. A region can have high revenue and still have a weak win rate if it's just throwing more leads at the funnel — win rate catches that. |
| **Naive Pipeline Value** | `SUM(deal_value)` for all open (not-yet-closed) deals | The "on paper" size of the pipeline. Useful as a ceiling, but should never be reported to leadership as expected revenue — see Weighted Forecast. |
| **Weighted Pipeline Forecast** | `SUM(deal_value × stage_win_probability)` for open deals (Lead 10%, Qualified 30%, Proposal 60%) | The realistic expected-revenue number. On this dataset, naive pipeline overstates reality by 71–74% — this metric is what should actually go into a revenue forecast, not the raw pipeline sum. |
| **Average Deal Size** | `AVG(deal_value)` where `stage = 'Closed Won'` | Tracks whether the business is moving upmarket/downmarket over time. A rising average deal size with flat deal count means bigger customers, not more customers. |
| **Pipeline Coverage Ratio** | `Weighted Forecast ÷ Monthly Target` | Answers "will this rep/region likely hit target?" A ratio near or above 1.0x means the weighted forecast alone covers target; below 1.0x signals a probable shortfall. (Note: the classic "3x-4x raw pipeline" industry heuristic doesn't apply here — see the Day 9 methodology note in the README for why.) |
| **Cohort Conversion Rate** | Cumulative % of a monthly lead cohort that reaches Closed Won, tracked by months since creation | Reveals how fast (or slow) leads actually convert, and whether that speed is improving cohort-over-cohort. Recent cohorts are right-censored (haven't had time to mature) and should not be compared directly against older, fully-matured cohorts. |
| **Forecast Accuracy (MAPE)** | Mean Absolute % Error between predicted value (via last-known-stage win probability) and actual outcome, by month | Validates whether the win-probability model itself is trustworthy. A high MAPE means the stage probabilities need recalibrating against this business's actual historical win rates rather than using generic assumptions. |

---

### Known Issue Worth Flagging
Two metrics can look similar but mean different things: **"Closed-Won deal value"** (what was agreed) vs. **"Paid revenue"** (what was collected). A deal can be Closed Won and still be Pending or Refunded in payment status. Always use Paid revenue for anything reported as actual business performance.
