from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from ..models.market_snapshot import MarketSnapshot
from ..models.security import SecurityIdentity
from ..analytics.ratio_calculator import percentage_change, safe_divide


class KiteQuoteClient(Protocol):
    def quote(self, instruments: list[str]) -> dict[str, Any]: ...


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


class KiteMarketProvider:
    def __init__(self, client: KiteQuoteClient) -> None:
        self.client = client

    def get_snapshot(self, identity: SecurityIdentity, now: datetime | None = None) -> MarketSnapshot:
        if not identity.kite_key:
            return MarketSnapshot(warnings=["SECURITY_IDENTITY_UNRESOLVED"])
        try:
            payload = self.client.quote([identity.kite_key])
        except Exception as exc:
            return MarketSnapshot(warnings=[f"KITE_QUOTE_FAILED:{type(exc).__name__}"])
        quote = payload.get(identity.kite_key) if isinstance(payload, dict) else None
        if not isinstance(quote, dict):
            return MarketSnapshot(warnings=["EXACT_KITE_QUOTE_UNAVAILABLE"])
        ohlc = quote.get("ohlc") if isinstance(quote.get("ohlc"), dict) else {}
        depth = quote.get("depth") if isinstance(quote.get("depth"), dict) else {}
        buys = depth.get("buy") if isinstance(depth.get("buy"), list) else []
        sells = depth.get("sell") if isinstance(depth.get("sell"), list) else []
        best_bid = _number(buys[0].get("price")) if buys and isinstance(buys[0], dict) else None
        best_ask = _number(sells[0].get("price")) if sells and isinstance(sells[0], dict) else None
        ltp = _number(quote.get("last_price"))
        previous_close = _number(ohlc.get("close"))
        high = _number(ohlc.get("high"))
        low = _number(ohlc.get("low"))
        volume = _number(quote.get("volume"))
        average_price = _number(quote.get("average_price"))
        buy_quantity = _number(quote.get("buy_quantity"))
        sell_quantity = _number(quote.get("sell_quantity"))
        timestamp_raw = quote.get("timestamp") or quote.get("last_trade_time")
        timestamp: datetime | None = None
        if isinstance(timestamp_raw, datetime):
            timestamp = timestamp_raw
        elif timestamp_raw:
            try:
                timestamp = datetime.fromisoformat(str(timestamp_raw).replace("Z", "+00:00"))
            except ValueError:
                timestamp = None
        reference_now = now or datetime.now(timezone.utc)
        if timestamp and timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        midpoint = None if best_bid is None or best_ask is None else (best_bid + best_ask) / 2
        spread = safe_divide(None if best_bid is None or best_ask is None else best_ask - best_bid, midpoint)
        imbalance = safe_divide(
            None if buy_quantity is None or sell_quantity is None else buy_quantity - sell_quantity,
            None if buy_quantity is None or sell_quantity is None else buy_quantity + sell_quantity,
        )
        day_position = safe_divide(
            None if ltp is None or low is None else ltp - low,
            None if high is None or low is None else high - low,
        )
        return MarketSnapshot(
            ltp=ltp,
            previous_close=previous_close,
            open=_number(ohlc.get("open")),
            day_high=high,
            day_low=low,
            volume=volume,
            average_traded_price=average_price,
            buy_quantity=buy_quantity,
            sell_quantity=sell_quantity,
            best_bid=best_bid,
            best_ask=best_ask,
            lower_circuit=_number(quote.get("lower_circuit_limit")),
            upper_circuit=_number(quote.get("upper_circuit_limit")),
            quote_timestamp=timestamp,
            day_return_pct=percentage_change(ltp, previous_close),
            bid_ask_spread_pct=None if spread is None else round(spread * 100, 4),
            estimated_traded_value=None if volume is None or average_price is None else volume * average_price,
            buy_sell_imbalance=None if imbalance is None else round(imbalance, 4),
            day_range_position_pct=None if day_position is None else round(day_position * 100, 2),
            quote_age_seconds=None if timestamp is None else max(0.0, (reference_now - timestamp).total_seconds()),
        )
