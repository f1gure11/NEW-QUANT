# Frozen Forward Research Status

Generated: `2026-08-31T11:07:21Z`

> Collection only. Maturity permits one frozen evaluation; it never permits paper or live trading.

| Strategy | Model | Status | Evidence |
| --- | --- | --- | --- |
| qqq_monthly_active_enhancement | `qqq-pit-1fda3d7e14f137bf` | collecting | observations=24, signalDecisionObservations=0, newSignalDates=[], forwardDays=23, completeMarketObservationRatio=1.0 |
| qqq_event_breakout_reversal_gate | `event-gate-ac84915dc46654fd` | collecting | observations=120, uniqueEvents=2, completeEvents=2, eventsPerFamily={'cpi': 1, 'pce': 1}, directionalDecisions=0 |
| spcx_1h_multi_horizon_momentum | `spcx-mhm-7be4e11ac843fb74` | collecting | observations=24, forwardDays=23, signalTransitions=11, completeMarketObservations=24, fundingObservations=24 |

## Checks

- `qqq-pit-1fda3d7e14f137bf`: newSignalDates: wait, forwardDays: wait, marketCoverage: pass
- `event-gate-ac84915dc46654fd`: completeEvents: wait, eventsPerFamily: wait, directionalDecisions: wait
- `spcx-mhm-7be4e11ac843fb74`: forwardDays: wait, signalTransitions: wait, completeMarketObservations: wait, fundingObservations: pass
