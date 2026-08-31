from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class EvidenceSource:
    kind: str
    title: str
    url: str
    contribution: str


@dataclass(frozen=True, slots=True)
class StrategyEvidence:
    strategy: str
    rationale: str
    sources: tuple[EvidenceSource, ...]


# Deliberately small allow-list: research implementation alone never implies
# live eligibility. Each entry still has to pass chronological, cost-stressed
# validation before the candidate gate can approve it.
STRATEGY_EVIDENCE: dict[str, StrategyEvidence] = {
    "time_series_momentum": StrategyEvidence(
        strategy="time_series_momentum",
        rationale="Lagged own-return direction with volatility-normalized sizing.",
        sources=(
            EvidenceSource(
                kind="journal",
                title="Time Series Momentum — Moskowitz, Ooi and Pedersen (2012)",
                url="https://doi.org/10.1016/j.jfineco.2011.11.003",
                contribution="Sign of an asset's lagged own return as the directional forecast.",
            ),
            EvidenceSource(
                kind="journal",
                title="Risks and Returns of Cryptocurrency — Liu and Tsyvinski (2021)",
                url="https://doi.org/10.1093/rfs/hhaa113",
                contribution="Crypto-specific empirical support for time-series momentum.",
            ),
            EvidenceSource(
                kind="github",
                title="pysystemtrade",
                url="https://github.com/pst-group/pysystemtrade",
                contribution="Reference for volatility-normalized systematic trend architecture; no code copied.",
            ),
        ),
    ),
    "multi_horizon_momentum": StrategyEvidence(
        strategy="multi_horizon_momentum",
        rationale="Diversified lagged-return forecasts across several horizons, with persistent position state.",
        sources=(
            EvidenceSource(
                kind="journal",
                title="A Century of Evidence on Trend-Following Investing — Hurst, Ooi and Pedersen (2017)",
                url="https://doi.org/10.3905/jpm.2017.44.1.015",
                contribution="Diversification of trend forecasts across multiple horizons.",
            ),
            EvidenceSource(
                kind="journal",
                title="Volatility-Managed Portfolios — Moreira and Muir (2017)",
                url="https://doi.org/10.1111/jofi.12513",
                contribution="Reduce notional exposure when recent realized volatility rises.",
            ),
            EvidenceSource(
                kind="github",
                title="pysystemtrade",
                url="https://github.com/pst-group/pysystemtrade",
                contribution="Reference for diversified trend forecasts and risk scaling; no code copied.",
            ),
        ),
    ),
}


def is_strategy_evidence_backed(strategy: str) -> bool:
    evidence = STRATEGY_EVIDENCE.get(str(strategy))
    if evidence is None or not evidence.sources:
        return False
    return all(source.kind in {"journal", "github"} and source.url.startswith("https://") for source in evidence.sources)


def evidence_payload(strategy: str) -> dict[str, Any] | None:
    evidence = STRATEGY_EVIDENCE.get(str(strategy))
    if evidence is None or not is_strategy_evidence_backed(strategy):
        return None
    return asdict(evidence)
