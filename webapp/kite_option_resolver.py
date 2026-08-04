"""Resolve Kite NFO option contracts for 5%/10% spread construction."""

from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
import math
from typing import Any

import kite_spread_config as spread_cfg


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def strike_step_for_spot(spot: float) -> int:
    """DHAN stock-option target grid: next 50-point OTM strike."""

    return 50


def next_otm_strike(value: float, option_type: str, step: int = 50) -> float:
    """Round to the nearest usable stock-option strike grid.

    DHAN/DHAN-IT uses a softer 50-point grid rule for stock options:
    stay on the lower rounded strike when the remainder is 30 points or less,
    and move to the next 50-point strike only when the remainder is above 30.
    This avoids pushing 5%/10% targets too far away from the actual CMP.
    """

    clean_step = max(int(step or 50), 1)
    clean_value = _to_float(value)
    lower = math.floor(clean_value / clean_step) * clean_step
    remainder = clean_value - lower
    if remainder > 30:
        return float(lower + clean_step)
    return float(lower)


def _parse_expiry(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d %b %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


@lru_cache(maxsize=2)
def cached_nfo_instruments_for_day(cache_key: str, adapter_id: int, adapter: Any) -> tuple[dict[str, Any], ...]:
    return tuple(dict(row) for row in adapter.get_instruments("NFO"))


class KiteOptionResolver:
    def __init__(self, instruments: list[dict[str, Any]] | None = None, broker: Any | None = None, today: date | None = None) -> None:
        self._instruments = instruments
        self.broker = broker
        self.today = today or date.today()

    def instruments(self) -> list[dict[str, Any]]:
        if self._instruments is not None:
            return self._instruments
        if self.broker is None:
            return []
        cache_key = self.today.isoformat()
        self._instruments = list(cached_nfo_instruments_for_day(cache_key, id(self.broker), self.broker))
        return self._instruments

    def option_contracts(self, underlying: str, option_type: str, expiry: str | date | None = None) -> list[dict[str, Any]]:
        symbol = str(underlying or "").upper()
        opt = str(option_type or "").upper()
        expiry_date = _parse_expiry(expiry) if expiry else None
        rows = []
        for row in self.instruments():
            if str(row.get("name") or row.get("underlying") or "").upper() != symbol:
                continue
            if str(row.get("instrument_type") or row.get("option_type") or "").upper() != opt:
                continue
            if expiry_date and _parse_expiry(row.get("expiry")) != expiry_date:
                continue
            rows.append(row)
        return rows

    def monthly_expiries(self, underlying: str) -> list[date]:
        expiries = sorted({
            parsed
            for row in self.instruments()
            if str(row.get("name") or row.get("underlying") or "").upper() == str(underlying).upper()
            if (parsed := _parse_expiry(row.get("expiry"))) is not None and parsed >= self.today
        })
        return expiries

    def selected_expiry(self, underlying: str, requested: str | date | None = None) -> date | None:
        expiries = self.monthly_expiries(underlying)
        requested_date = _parse_expiry(requested)
        if requested_date in expiries and (requested_date - self.today).days >= spread_cfg.BLOCK_EXPIRY_WITHIN_DAYS:
            return requested_date
        safe = [item for item in expiries if (item - self.today).days >= spread_cfg.BLOCK_EXPIRY_WITHIN_DAYS]
        return safe[0] if safe else (expiries[0] if expiries else requested_date)

    def nearest_contract(self, underlying: str, expiry: str | date, option_type: str, target_strike: float) -> dict[str, Any] | None:
        contracts = self.option_contracts(underlying, option_type, expiry)
        if not contracts:
            return None
        return min(contracts, key=lambda row: abs(_to_float(row.get("strike")) - target_strike))

    def nearest_contract_after_excluding(
        self,
        underlying: str,
        expiry: str | date,
        option_type: str,
        target_strike: float,
        excluded_strikes: set[float] | None = None,
    ) -> dict[str, Any] | None:
        excluded = excluded_strikes or set()
        contracts = [
            row
            for row in self.option_contracts(underlying, option_type, expiry)
            if _to_float(row.get("strike")) not in excluded
        ]
        if not contracts:
            return None
        return min(contracts, key=lambda row: abs(_to_float(row.get("strike")) - target_strike))

    def otm_contract_after_excluding(
        self,
        underlying: str,
        expiry: str | date,
        option_type: str,
        target_strike: float,
        excluded_strikes: set[float] | None = None,
    ) -> dict[str, Any] | None:
        opt = str(option_type or "").upper()
        excluded = excluded_strikes or set()
        contracts = [
            row
            for row in self.option_contracts(underlying, option_type, expiry)
            if _to_float(row.get("strike")) not in excluded
        ]
        if not contracts:
            return None
        if opt == "CE":
            otm = [row for row in contracts if _to_float(row.get("strike")) >= target_strike]
            return min(otm, key=lambda row: _to_float(row.get("strike"))) if otm else self.nearest_contract_after_excluding(underlying, expiry, option_type, target_strike, excluded)
        otm = [row for row in contracts if _to_float(row.get("strike")) <= target_strike]
        return max(otm, key=lambda row: _to_float(row.get("strike"))) if otm else self.nearest_contract_after_excluding(underlying, expiry, option_type, target_strike, excluded)

    def resolve_spread_legs(self, symbol: str, spot: float, expiry: str | date | None, strategy: str) -> dict[str, Any]:
        strategy_type = str(strategy or "").upper()
        option_type = "CE" if strategy_type == "BEAR_CALL_SPREAD" else "PE"
        selected_expiry = self.selected_expiry(symbol, expiry)
        if selected_expiry is None:
            return {"error": "CONTRACT_UNRESOLVED"}
        strike_step = strike_step_for_spot(spot)
        raw_sell_target = spot * (1.05 if option_type == "CE" else 0.95)
        raw_hedge_target = spot * (1.10 if option_type == "CE" else 0.90)
        sell_target = next_otm_strike(raw_sell_target, option_type, strike_step)
        hedge_target = next_otm_strike(raw_hedge_target, option_type, strike_step)
        sell = self.otm_contract_after_excluding(symbol, selected_expiry, option_type, sell_target)
        sell_strike_for_exclusion = {_to_float(sell.get("strike"))} if sell else set()
        hedge = self.otm_contract_after_excluding(symbol, selected_expiry, option_type, hedge_target, sell_strike_for_exclusion)
        if sell and hedge:
            sell_strike = _to_float(sell.get("strike"))
            hedge_strike = _to_float(hedge.get("strike"))
            if option_type == "CE" and hedge_strike <= sell_strike:
                hedge = None
            if option_type == "PE" and hedge_strike >= sell_strike:
                hedge = None
        if not sell or not hedge:
            return {"error": "CONTRACT_UNRESOLVED", "expiry": selected_expiry.isoformat()}
        return {
            "expiry": selected_expiry.isoformat(),
            "sell_leg": dict(sell),
            "buy_leg": dict(hedge),
            "lot_size": int(float(sell.get("lot_size") or hedge.get("lot_size") or 0)),
            "strike_step": strike_step,
            "sell_target_strike": _to_float(sell.get("strike")),
            "hedge_target_strike": _to_float(hedge.get("strike")),
            "raw_sell_target_strike": raw_sell_target,
            "raw_hedge_target_strike": raw_hedge_target,
        }
