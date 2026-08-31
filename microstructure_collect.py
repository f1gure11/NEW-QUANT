from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from market_selector import MarketSelectorConfig, dec, select_candidates
from okx_client import OkxRestClient


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = PROJECT_ROOT / "data" / "microstructure"
LAKE_OUTPUT_ROOT = PROJECT_ROOT / "data_lake" / "snapshots"
DEFAULT_FORWARD_REGISTRY = PROJECT_ROOT / "config" / "qqq_pure_stock_microstructure_forward_preregistration.json"


@dataclass(slots=True)
class BookStats:
    mid: float
    spread_bps: float
    bid_depth_5: float
    ask_depth_5: float
    bid_depth_10: float
    ask_depth_10: float
    imbalance_5: float
    imbalance_10: float


@dataclass(slots=True)
class TradeStats:
    buy_count: int
    sell_count: int
    buy_notional: float
    sell_notional: float
    imbalance: float
    last_trade_ts: int


def main() -> int:
    args = parse_args()
    client = public_client_from_env()
    registry = load_forward_registry(Path(args.forward_registry)) if args.forward_registry else None
    forward_inst_ids = forward_instruments(registry) if registry else []
    inst_ids = resolve_inst_ids(client, args, additional_inst_ids=forward_inst_ids)
    instrument_metadata = fetch_instrument_metadata(client, inst_ids)
    if registry:
        validate_forward_instrument_metadata(instrument_metadata, forward_inst_ids)
    output_root = Path(args.output_root)
    lake_output_root = Path(args.lake_output_root) if args.lake_output_root else None
    samples = 1 if args.once else max(1, int(args.samples))
    written = 0
    for sample_index in range(samples):
        captured_at = now_iso()
        for inst_id in inst_ids:
            research = forward_snapshot_metadata(registry) if inst_id in forward_inst_ids else None
            try:
                snapshot = fetch_microstructure_snapshot(
                    client,
                    inst_id,
                    books_size=args.books_size,
                    trades_limit=args.trades_limit,
                    captured_at=captured_at,
                    instrument=instrument_metadata.get(inst_id),
                    research=research,
                )
            except Exception as exc:
                snapshot = {"capturedAt": captured_at, "instId": inst_id, "ok": False, "error": str(exc)}
                if research:
                    snapshot["research"] = research
            append_snapshot(output_root, snapshot)
            if lake_output_root and lake_output_root.resolve() != output_root.resolve():
                append_snapshot(lake_output_root, snapshot)
            written += 1
            time.sleep(max(0.0, float(args.sleep)))
        if sample_index < samples - 1:
            time.sleep(max(0.0, float(args.interval_seconds)))
    print(
        json.dumps(
            {
                "microstructureCollector": {
                    "instIds": inst_ids,
                    "snapshotsWritten": written,
                    "outputRoot": str(output_root),
                    "lakeOutputRoot": str(lake_output_root) if lake_output_root else None,
                    "forwardModelId": registry["study"]["modelId"] if registry else None,
                    "forwardInstrumentCount": len(forward_inst_ids),
                }
            },
            indent=2,
        )
    )
    return 0


def public_client_from_env() -> OkxRestClient:
    return OkxRestClient(
        base_url=os.getenv("OKX_BASE_URL", "https://www.okx.com").rstrip("/"),
        proxy_url=os.getenv("OKX_PROXY", ""),
        user_agent=os.getenv("OKX_USER_AGENT", "curl/8.10.1"),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect read-only OKX public microstructure snapshots for later unbiased research.")
    parser.add_argument("--inst-id", action="append", default=[], help="Instrument to collect. Can be repeated. Defaults to public top-N.")
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--min-quote-volume", default="5000000")
    parser.add_argument("--max-spread-bps", default="20")
    parser.add_argument("--books-size", type=int, default=50)
    parser.add_argument("--trades-limit", type=int, default=100)
    parser.add_argument("--samples", type=int, default=1)
    parser.add_argument("--interval-seconds", type=float, default=60.0)
    parser.add_argument("--sleep", type=float, default=0.12)
    parser.add_argument("--once", action="store_true", help="Collect one sample for each instrument and exit.")
    parser.add_argument("--output-root", default=str(OUTPUT_ROOT))
    parser.add_argument("--lake-output-root", default="", help="Optional second append-only snapshot root, normally data_lake/snapshots.")
    parser.add_argument("--forward-registry", default="", help="Frozen forward registry whose instruments are added to collection.")
    return parser.parse_args()


def resolve_inst_ids(
    client: OkxRestClient,
    args: argparse.Namespace,
    *,
    additional_inst_ids: list[str] | None = None,
) -> list[str]:
    explicit = [str(item) for item in args.inst_id if item]
    additional = [str(item) for item in (additional_inst_ids or []) if item]
    if explicit or additional:
        return list(dict.fromkeys([*explicit, *additional]))
    candidates = select_candidates(
        client,
        MarketSelectorConfig(
            min_quote_volume=dec(args.min_quote_volume),
            max_spread_bps=dec(args.max_spread_bps),
            top_n=max(0, int(args.top_n)),
        ),
    )
    return [candidate.inst_id for candidate in candidates]


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def derived_id(prefix: str, value: dict[str, Any]) -> str:
    return f"{prefix}-{hashlib.sha256(canonical_json(value)).hexdigest()[:16]}"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_forward_registry(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("forward registry must be a JSON object")
    validate_forward_registry(payload)
    return payload


def validate_forward_registry(registry: dict[str, Any]) -> None:
    required = {"schemaVersion", "registryId", "frozenAt", "protocol", "study"}
    if required - set(registry):
        raise ValueError(f"forward registry missing fields: {sorted(required - set(registry))}")
    registry_basis = {key: registry[key] for key in ("frozenAt", "protocol", "study")}
    if registry.get("registryId") != derived_id("qqq-stock-microstructure-registry", registry_basis):
        raise ValueError("registryId does not match frozen forward content")
    study = registry["study"]
    if study.get("modelId") != derived_id("qqq-stock-microstructure", study["basis"]):
        raise ValueError("modelId does not match frozen study basis")
    if study.get("status") != "preregistered_collecting" or study.get("paperOrLiveAuthorized") is not False:
        raise ValueError("forward study must remain preregistered_collecting and trading-disabled")
    if study.get("forwardBoundary") != registry.get("frozenAt"):
        raise ValueError("forwardBoundary must equal frozenAt")
    boundary = datetime.fromisoformat(str(study["forwardBoundary"]).replace("Z", "+00:00"))
    if boundary > datetime.now(timezone.utc):
        raise ValueError("forwardBoundary cannot be in the future")
    universe = study.get("universe", {})
    symbols = universe.get("symbols", [])
    instruments = universe.get("instruments", [])
    if len(symbols) != 29 or symbols != sorted(set(symbols)) or "DASH" in symbols:
        raise ValueError("frozen equity universe must contain 29 sorted unique non-DASH symbols")
    if instruments != [f"{symbol}-USDT-SWAP" for symbol in symbols]:
        raise ValueError("frozen instruments must exactly map the 29 equity symbols")
    artifacts = study.get("artifacts", [])
    for artifact in artifacts:
        artifact_path = PROJECT_ROOT / str(artifact["path"])
        if not artifact_path.is_file() or sha256_path(artifact_path) != artifact["sha256"]:
            raise ValueError(f"frozen artifact changed or is missing: {artifact_path}")
    source_registry_path = PROJECT_ROOT / str(study["source"]["monteCarloRegistryPath"])
    source_registry = json.loads(source_registry_path.read_text(encoding="utf-8"))
    source_symbols = source_registry.get("study", {}).get("universe", {}).get("symbols", [])
    if symbols != source_symbols:
        raise ValueError("forward universe no longer matches the frozen Monte Carlo universe")
    maturity = study.get("maturity", {})
    if int(maturity.get("minimumCompleteCalendarMonths", 0)) < 12:
        raise ValueError("forward maturity cannot be shorter than 12 complete calendar months")
    if int(maturity.get("minimumIndependentReductionEvents", 0)) < 100:
        raise ValueError("forward maturity requires at least 100 independent reduction events")


def forward_instruments(registry: dict[str, Any]) -> list[str]:
    return list(registry["study"]["universe"]["instruments"])


def forward_snapshot_metadata(registry: dict[str, Any]) -> dict[str, Any]:
    study = registry["study"]
    return {
        "schemaVersion": 1,
        "registryId": registry["registryId"],
        "modelId": study["modelId"],
        "strategyKey": study["strategyKey"],
        "forwardBoundary": study["forwardBoundary"],
        "observationOnly": True,
        "historyReplayUsed": False,
        "paperOrLiveAuthorized": False,
    }


def fetch_instrument_metadata(client: OkxRestClient, inst_ids: list[str]) -> dict[str, dict[str, Any]]:
    try:
        rows = client.request("GET", "/api/v5/public/instruments", params={"instType": "SWAP"}).get("data", [])
    except Exception:
        return {}
    wanted = set(inst_ids)
    return {
        str(row.get("instId")): row
        for row in rows
        if isinstance(row, dict) and str(row.get("instId")) in wanted
    }


def validate_forward_instrument_metadata(
    metadata: dict[str, dict[str, Any]],
    inst_ids: list[str],
) -> None:
    missing = [inst_id for inst_id in inst_ids if inst_id not in metadata]
    if missing:
        raise ValueError(f"forward instruments missing public metadata: {missing}")
    invalid = [
        inst_id
        for inst_id in inst_ids
        if metadata[inst_id].get("state") != "live"
        or str(metadata[inst_id].get("instCategory")) != "3"
        or decimal_value(metadata[inst_id].get("ctVal")) <= 0
    ]
    if invalid:
        raise ValueError(f"forward instruments are not live category-3 contracts with ctVal: {invalid}")


def fetch_microstructure_snapshot(
    client: OkxRestClient,
    inst_id: str,
    *,
    books_size: int,
    trades_limit: int,
    captured_at: str | None = None,
    instrument: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
) -> dict[str, Any]:
    captured_at = captured_at or now_iso()
    ticker = first(client.request("GET", "/api/v5/market/ticker", params={"instId": inst_id}).get("data", []))
    book = first(client.request("GET", "/api/v5/market/books", params={"instId": inst_id, "sz": str(max(1, min(400, books_size)))}).get("data", []))
    trades = client.request("GET", "/api/v5/market/trades", params={"instId": inst_id, "limit": str(max(1, min(500, trades_limit)))}).get("data", [])
    open_interest = first(client.request("GET", "/api/v5/public/open-interest", params={"instType": "SWAP", "instId": inst_id}).get("data", []))
    funding = first(client.request("GET", "/api/v5/public/funding-rate", params={"instId": inst_id}).get("data", []))
    stats = book_stats(book, ticker)
    instrument = instrument or {}
    contract_value = instrument_contract_value(instrument, open_interest)
    trade_summary = trade_stats(trades, contract_value=contract_value)
    snapshot = {
        "schemaVersion": 2,
        "capturedAt": captured_at,
        "capturedTs": int(datetime.now(timezone.utc).timestamp() * 1000),
        "instId": inst_id,
        "ok": True,
        "dataComplete": snapshot_data_complete(ticker, book, trades, open_interest, funding),
        "instrument": compact_instrument(instrument),
        "ticker": compact_ticker(ticker),
        "book": compact_book(book),
        "trades": compact_trades(trades),
        "openInterest": open_interest,
        "funding": funding,
        "features": {
            "book": asdict(stats),
            "trades": asdict(trade_summary),
            "open_interest": open_interest_features(open_interest),
            "premium": premium_features(funding),
            "order_flow": {
                "sample_type": "latest_public_trades_at_capture",
                "requested_limit": max(1, min(500, trades_limit)),
                "returned_count": len(trades) if isinstance(trades, list) else 0,
                "contract_value": float(contract_value),
                **asdict(trade_summary),
            },
            "depth": depth_features(book, contract_value=contract_value, requested_levels=books_size),
        },
    }
    if research:
        snapshot["research"] = research
    return snapshot


def book_stats(book: dict[str, Any], ticker: dict[str, Any]) -> BookStats:
    bid = decimal_value(ticker.get("bidPx"))
    ask = decimal_value(ticker.get("askPx"))
    if bid <= 0:
        bid = best_price(book.get("bids", []))
    if ask <= 0:
        ask = best_price(book.get("asks", []))
    mid = (bid + ask) / Decimal("2") if bid > 0 and ask > 0 else Decimal("0")
    spread_bps = (ask - bid) / mid * Decimal("10000") if mid > 0 else Decimal("0")
    bids = book.get("bids", []) if isinstance(book.get("bids", []), list) else []
    asks = book.get("asks", []) if isinstance(book.get("asks", []), list) else []
    bid_5 = depth_notional(bids[:5])
    ask_5 = depth_notional(asks[:5])
    bid_10 = depth_notional(bids[:10])
    ask_10 = depth_notional(asks[:10])
    return BookStats(
        mid=float(mid),
        spread_bps=float(spread_bps),
        bid_depth_5=float(bid_5),
        ask_depth_5=float(ask_5),
        bid_depth_10=float(bid_10),
        ask_depth_10=float(ask_10),
        imbalance_5=float(imbalance(bid_5, ask_5)),
        imbalance_10=float(imbalance(bid_10, ask_10)),
    )


def trade_stats(trades: list[dict[str, Any]], *, contract_value: Decimal = Decimal("1")) -> TradeStats:
    buy_count = 0
    sell_count = 0
    buy_notional = Decimal("0")
    sell_notional = Decimal("0")
    last_ts = 0
    for trade in trades if isinstance(trades, list) else []:
        side = str(trade.get("side", ""))
        px = decimal_value(trade.get("px"))
        size = decimal_value(trade.get("sz"))
        notional = px * size * contract_value
        last_ts = max(last_ts, int(decimal_value(trade.get("ts"))))
        if side == "buy":
            buy_count += 1
            buy_notional += notional
        elif side == "sell":
            sell_count += 1
            sell_notional += notional
    return TradeStats(
        buy_count=buy_count,
        sell_count=sell_count,
        buy_notional=float(buy_notional),
        sell_notional=float(sell_notional),
        imbalance=float(imbalance(buy_notional, sell_notional)),
        last_trade_ts=last_ts,
    )


def append_snapshot(output_root: Path, snapshot: dict[str, Any]) -> Path:
    inst_id = safe_name(str(snapshot.get("instId", "unknown")))
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    path = output_root / inst_id / f"{day}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(snapshot, separators=(",", ":"), ensure_ascii=False) + "\n")
    return path


def compact_ticker(ticker: dict[str, Any]) -> dict[str, Any]:
    keys = ("instId", "ts", "last", "lastSz", "askPx", "askSz", "bidPx", "bidSz", "vol24h", "volCcy24h", "volCcyQuote24h")
    return {key: ticker.get(key, "") for key in keys}


def compact_instrument(instrument: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "instId",
        "instType",
        "instCategory",
        "state",
        "ctType",
        "ctVal",
        "ctValCcy",
        "settleCcy",
        "lotSz",
        "minSz",
        "tickSz",
    )
    return {key: instrument.get(key, "") for key in keys}


def compact_book(book: dict[str, Any]) -> dict[str, Any]:
    return {
        "ts": book.get("ts", ""),
        "bids": compact_book_rows(book.get("bids", [])),
        "asks": compact_book_rows(book.get("asks", [])),
    }


def compact_book_rows(rows: Any) -> list[list[str]]:
    if not isinstance(rows, list):
        return []
    return [[str(item[0]), str(item[1])] for item in rows if isinstance(item, list) and len(item) >= 2]


def compact_trades(trades: Any) -> list[dict[str, str]]:
    if not isinstance(trades, list):
        return []
    result = []
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        result.append(
            {
                "ts": str(trade.get("ts", "")),
                "side": str(trade.get("side", "")),
                "px": str(trade.get("px", "")),
                "sz": str(trade.get("sz", "")),
                "tradeId": str(trade.get("tradeId", "")),
            }
        )
    return result


def snapshot_data_complete(
    ticker: dict[str, Any],
    book: dict[str, Any],
    trades: Any,
    open_interest: dict[str, Any],
    funding: dict[str, Any],
) -> bool:
    return bool(
        ticker
        and book.get("bids")
        and book.get("asks")
        and isinstance(trades, list)
        and trades
        and open_interest.get("oi") not in (None, "")
        and funding.get("premium") not in (None, "")
    )


def instrument_contract_value(
    instrument: dict[str, Any],
    open_interest: dict[str, Any],
) -> Decimal:
    value = decimal_value(instrument.get("ctVal"))
    if value <= 0:
        value = decimal_value(open_interest.get("ctVal"))
    return value if value > 0 else Decimal("1")


def open_interest_features(open_interest: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": int(decimal_value(open_interest.get("ts"))),
        "contracts": float(decimal_value(open_interest.get("oi"))),
        "underlying_units": float(decimal_value(open_interest.get("oiCcy"))),
        "usd": float(decimal_value(open_interest.get("oiUsd"))),
    }


def premium_features(funding: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": int(decimal_value(funding.get("ts"))),
        "premium_rate": float(decimal_value(funding.get("premium"))),
        "funding_rate": float(decimal_value(funding.get("fundingRate"))),
        "next_funding_rate": float(decimal_value(funding.get("nextFundingRate"))),
        "funding_time": int(decimal_value(funding.get("fundingTime"))),
        "next_funding_time": int(decimal_value(funding.get("nextFundingTime"))),
    }


def depth_features(
    book: dict[str, Any],
    *,
    contract_value: Decimal,
    requested_levels: int,
) -> dict[str, Any]:
    bids = book.get("bids", []) if isinstance(book.get("bids"), list) else []
    asks = book.get("asks", []) if isinstance(book.get("asks"), list) else []
    result: dict[str, Any] = {
        "timestamp": int(decimal_value(book.get("ts"))),
        "requested_levels": max(1, min(400, int(requested_levels))),
        "returned_bid_levels": len(bids),
        "returned_ask_levels": len(asks),
        "contract_value": float(contract_value),
    }
    for levels in (5, 10, 25, 50):
        bid_contracts = depth_contracts(bids[:levels])
        ask_contracts = depth_contracts(asks[:levels])
        bid_notional = depth_notional(bids[:levels]) * contract_value
        ask_notional = depth_notional(asks[:levels]) * contract_value
        result[f"bid_contracts_{levels}"] = float(bid_contracts)
        result[f"ask_contracts_{levels}"] = float(ask_contracts)
        result[f"bid_notional_{levels}"] = float(bid_notional)
        result[f"ask_notional_{levels}"] = float(ask_notional)
        result[f"imbalance_{levels}"] = float(imbalance(bid_notional, ask_notional))
    return result


def depth_notional(rows: list[list[Any]]) -> Decimal:
    total = Decimal("0")
    for row in rows:
        if len(row) >= 2:
            total += decimal_value(row[0]) * decimal_value(row[1])
    return total


def depth_contracts(rows: list[list[Any]]) -> Decimal:
    return sum((decimal_value(row[1]) for row in rows if len(row) >= 2), Decimal("0"))


def imbalance(left: Decimal, right: Decimal) -> Decimal:
    total = left + right
    return (left - right) / total if total > 0 else Decimal("0")


def best_price(rows: Any) -> Decimal:
    if isinstance(rows, list) and rows and isinstance(rows[0], list) and rows[0]:
        return decimal_value(rows[0][0])
    return Decimal("0")


def decimal_value(value: Any) -> Decimal:
    try:
        if value in (None, ""):
            return Decimal("0")
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def first(values: Any) -> dict[str, Any]:
    if isinstance(values, list) and values and isinstance(values[0], dict):
        return values[0]
    return {}


def safe_name(value: str) -> str:
    return value.lower().replace("-", "_").replace("/", "_")


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


if __name__ == "__main__":
    raise SystemExit(main())
