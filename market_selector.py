from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from okx_client import OkxRestClient


@dataclass(slots=True)
class MarketSelectorConfig:
    min_quote_volume: Decimal = Decimal("5000000")
    max_spread_bps: Decimal = Decimal("20")
    top_n: int = 20
    require_live: bool = True


@dataclass(slots=True)
class MarketCandidate:
    inst_id: str
    inst_family: str
    base_ccy: str
    quote_ccy: str
    settle_ccy: str
    ct_val: Decimal
    tick_sz: Decimal
    lot_sz: Decimal
    min_sz: Decimal
    state: str
    last: Decimal
    bid_px: Decimal
    ask_px: Decimal
    spread_bps: Decimal
    quote_volume_24h: Decimal
    volume_24h: Decimal


def fetch_swap_instruments(client: OkxRestClient) -> list[dict[str, Any]]:
    return client.request("GET", "/api/v5/public/instruments", params={"instType": "SWAP"}).get("data", [])


def fetch_swap_tickers(client: OkxRestClient) -> list[dict[str, Any]]:
    return client.request("GET", "/api/v5/market/tickers", params={"instType": "SWAP"}).get("data", [])


def select_candidates(client: OkxRestClient, config: MarketSelectorConfig) -> list[MarketCandidate]:
    instruments = fetch_swap_instruments(client)
    tickers = fetch_swap_tickers(client)
    return select_candidates_from_payloads(instruments, tickers, config)


def select_candidates_from_payloads(
    instruments: list[dict[str, Any]],
    tickers: list[dict[str, Any]],
    config: MarketSelectorConfig,
) -> list[MarketCandidate]:
    ticker_by_inst = {str(item.get("instId", "")): item for item in tickers}
    candidates: list[MarketCandidate] = []
    for instrument in instruments:
        if not is_usdt_perpetual_swap(instrument, require_live=config.require_live):
            continue
        ticker = ticker_by_inst.get(str(instrument.get("instId", "")))
        if not ticker:
            continue
        candidate = candidate_from_payload(instrument, ticker)
        if not candidate:
            continue
        if candidate.quote_volume_24h < config.min_quote_volume:
            continue
        if candidate.spread_bps > config.max_spread_bps:
            continue
        candidates.append(candidate)

    candidates.sort(key=lambda item: item.quote_volume_24h, reverse=True)
    return candidates[: max(0, config.top_n)]


def is_usdt_perpetual_swap(instrument: dict[str, Any], *, require_live: bool = True) -> bool:
    inst_id = str(instrument.get("instId", ""))
    if not inst_id.endswith("-USDT-SWAP"):
        return False
    if str(instrument.get("instType", "SWAP")) != "SWAP":
        return False
    if str(instrument.get("settleCcy", "")) != "USDT":
        return False
    quote_ccy = str(instrument.get("quoteCcy", "USDT"))
    if quote_ccy and quote_ccy != "USDT":
        return False
    if require_live and str(instrument.get("state", "")) != "live":
        return False
    return True


def candidate_from_payload(instrument: dict[str, Any], ticker: dict[str, Any]) -> MarketCandidate | None:
    inst_id = str(instrument.get("instId", ""))
    id_parts = inst_id.split("-")
    base_ccy = str(instrument.get("baseCcy") or (id_parts[0] if len(id_parts) >= 3 else ""))
    quote_ccy = str(instrument.get("quoteCcy") or (id_parts[1] if len(id_parts) >= 3 else "USDT"))
    ct_val = dec(instrument.get("ctVal"))
    tick_sz = dec(instrument.get("tickSz"))
    lot_sz = dec(instrument.get("lotSz"))
    min_sz = dec(instrument.get("minSz"))
    last = dec(ticker.get("last"))
    bid_px = dec(ticker.get("bidPx"))
    ask_px = dec(ticker.get("askPx"))
    if not inst_id or ct_val <= 0 or tick_sz <= 0 or lot_sz <= 0 or min_sz <= 0:
        return None
    if last <= 0 or bid_px <= 0 or ask_px <= 0 or ask_px < bid_px:
        return None

    mid = (bid_px + ask_px) / Decimal("2")
    if mid <= 0:
        return None
    spread_bps = (ask_px - bid_px) / mid * Decimal("10000")
    quote_volume_24h = quote_volume(ticker, last, ct_val)
    if quote_volume_24h <= 0:
        return None

    return MarketCandidate(
        inst_id=inst_id,
        inst_family=str(instrument.get("instFamily", "")),
        base_ccy=base_ccy,
        quote_ccy=quote_ccy,
        settle_ccy=str(instrument.get("settleCcy", "")),
        ct_val=ct_val,
        tick_sz=tick_sz,
        lot_sz=lot_sz,
        min_sz=min_sz,
        state=str(instrument.get("state", "")),
        last=last,
        bid_px=bid_px,
        ask_px=ask_px,
        spread_bps=spread_bps,
        quote_volume_24h=quote_volume_24h,
        volume_24h=dec(ticker.get("vol24h")),
    )


def quote_volume(ticker: dict[str, Any], last: Decimal, ct_val: Decimal) -> Decimal:
    direct = dec(ticker.get("volCcyQuote24h"))
    if direct > 0:
        return direct
    base_volume = dec(ticker.get("volCcy24h"))
    if base_volume > 0 and last > 0:
        return base_volume * last
    contract_volume = dec(ticker.get("vol24h"))
    if contract_volume > 0 and ct_val > 0 and last > 0:
        return contract_volume * ct_val * last
    return Decimal("0")


def selector_config_to_dict(config: MarketSelectorConfig) -> dict[str, Any]:
    return jsonable(asdict(config))


def candidate_to_dict(candidate: MarketCandidate) -> dict[str, Any]:
    return jsonable(asdict(candidate))


def jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return plain(value)
    if isinstance(value, dict):
        return {key: jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [jsonable(item) for item in value]
    return value


def dec(value: Any, default: Decimal = Decimal("0")) -> Decimal:
    try:
        if value in (None, ""):
            return default
        return Decimal(str(value))
    except Exception:
        return default


def plain(value: Decimal) -> str:
    return format(value.normalize(), "f")
