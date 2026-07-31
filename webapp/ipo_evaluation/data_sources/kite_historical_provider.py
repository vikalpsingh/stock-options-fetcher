from __future__ import annotations

import math
from datetime import date, timedelta
from statistics import mean, pstdev
from typing import Any, Protocol

from ..analytics.ratio_calculator import percentage_change
from ..analytics.return_calculator import calculate_period_returns, normalise_daily_candles
from ..models.market_snapshot import MarketSnapshot


class KiteHistoricalClient(Protocol):
    def historical_data(
        self,
        instrument_token: int,
        from_date: date,
        to_date: date,
        interval: str,
    ) -> list[dict[str, Any]]: ...


class KiteHistoricalProvider:
    def __init__(self, client: KiteHistoricalClient) -> None:
        self.client = client

    def enrich(
        self,
        snapshot: MarketSnapshot,
        instrument_token: int,
        listing_date: date,
        today: date | None = None,
    ) -> MarketSnapshot:
        end = today or date.today()
        try:
            candles = self.client.historical_data(instrument_token, listing_date, end, "day")
        except Exception as exc:
            return snapshot.model_copy(update={"warnings": [*snapshot.warnings, f"KITE_HISTORY_FAILED:{type(exc).__name__}"]})
        clean = normalise_daily_candles(candles)
        closes = [float(row["close"]) for row in clean]
        volumes = [float(row.get("volume") or 0) for row in clean]
        if not closes:
            return snapshot.model_copy(update={"warnings": [*snapshot.warnings, "INSUFFICIENT_TRADING_HISTORY"]})
        returns = [(closes[index] / closes[index - 1] - 1) for index in range(1, len(closes)) if closes[index - 1] > 0]
        high_52w = max(closes[-252:])
        low_52w = min(closes[-252:])
        peak = closes[0]
        max_drawdown = 0.0
        for close in closes:
            peak = max(peak, close)
            max_drawdown = min(max_drawdown, close / peak - 1)
        warnings = list(snapshot.warnings)
        period_returns, return_warnings = calculate_period_returns(clean, current_price=snapshot.ltp)
        warnings.extend(return_warnings)
        updates = {
            **period_returns,
            "average_volume_20d": mean(volumes[-20:]) if len(volumes) >= 20 else None,
            "average_traded_value_20d": mean(
                [closes[index] * volumes[index] for index in range(max(0, len(closes) - 20), len(closes))]
            ) if len(closes) >= 20 else None,
            "annualized_volatility_30d": pstdev(returns[-30:]) * math.sqrt(252) * 100 if len(returns) >= 30 else None,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "drawdown_from_52w_high_pct": percentage_change(closes[-1], high_52w),
            "distance_from_52w_low_pct": percentage_change(closes[-1], low_52w),
            "moving_average_20d": mean(closes[-20:]) if len(closes) >= 20 else None,
            "moving_average_50d": mean(closes[-50:]) if len(closes) >= 50 else None,
            "moving_average_200d": mean(closes[-200:]) if len(closes) >= 200 else None,
            "maximum_drawdown_pct": round(max_drawdown * 100, 2),
            "zero_volume_days_20d": sum(1 for volume in volumes[-20:] if volume == 0) if len(volumes) >= 20 else None,
            "warnings": warnings,
        }
        return snapshot.model_copy(update=updates)
