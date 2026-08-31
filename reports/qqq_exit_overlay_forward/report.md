# QQQ Exit Overlay Forward Study

Updated: `2026-08-31T01:17:46Z`
Boundary: `2026-08-10T17:05:00Z`
Status: `collecting` / `collecting`

> Public forward observation only. No history replay, account access, orders, paper authorization, or live authorization.

| Variant | Gross | Funding | Cost | Net | Double cost | Latency +1 bar |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| monthly_control | 0.0523% | -0.0052% | 0.0072% | 0.0400% | 0.0328% | 0.0394% |
| fixed_take_profit_10pct | 0.2904% | -0.0007% | 0.0105% | 0.2792% | 0.2687% | 0.2796% |
| trailing_profit_6pct_4pct | 0.3007% | 0.0006% | 0.0109% | 0.2904% | 0.2795% | 0.2982% |
| biweekly_20session_trend_review | 0.0523% | -0.0052% | 0.0072% | 0.0400% | 0.0328% | 0.0394% |

| Variant | Turnover | PF | Drawdown | Worst day | Closed | Open | Exit reasons |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| monthly_control | 7.1564% | 0.000 | 0.2170% | -0.0844% | 2 | 9 | stop_loss:2 |
| fixed_take_profit_10pct | 10.5460% | 8.151 | 0.2081% | -0.0958% | 7 | 4 | stop_loss:2, take_profit:5 |
| trailing_profit_6pct_4pct | 10.9163% | 6.540 | 0.1797% | -0.0872% | 7 | 4 | stop_loss:2, trailing_take_profit:5 |
| biweekly_20session_trend_review | 7.1564% | 0.000 | 0.2170% | -0.0844% | 2 | 9 | stop_loss:2 |

## Maturity

- forwardDays: wait
- monthlyCohorts: wait
- closedCandidateLegs: wait
- candidateExitEvents: wait
- marketCoverage: pass
