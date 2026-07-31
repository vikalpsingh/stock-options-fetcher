from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MarketSnapshot(BaseModel):
    ltp: float | None = None
    previous_close: float | None = None
    open: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    volume: float | None = None
    average_traded_price: float | None = None
    buy_quantity: float | None = None
    sell_quantity: float | None = None
    best_bid: float | None = None
    best_ask: float | None = None
    lower_circuit: float | None = None
    upper_circuit: float | None = None
    quote_timestamp: datetime | None = None
    day_return_pct: float | None = None
    bid_ask_spread_pct: float | None = None
    estimated_traded_value: float | None = None
    buy_sell_imbalance: float | None = None
    day_range_position_pct: float | None = None
    quote_age_seconds: float | None = None
    one_week_return_pct: float | None = None
    one_month_return_pct: float | None = None
    three_month_return_pct: float | None = None
    six_month_return_pct: float | None = None
    one_year_return_pct: float | None = None
    return_since_listing_pct: float | None = None
    gain_from_ipo_price_pct: float | None = None
    average_volume_20d: float | None = None
    average_traded_value_20d: float | None = None
    annualized_volatility_30d: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    drawdown_from_52w_high_pct: float | None = None
    distance_from_52w_low_pct: float | None = None
    moving_average_20d: float | None = None
    moving_average_50d: float | None = None
    moving_average_200d: float | None = None
    maximum_drawdown_pct: float | None = None
    zero_volume_days_20d: int | None = None
    circuit_limit_frequency: float | None = None
    free_float_pct: float | None = None
    warnings: list[str] = Field(default_factory=list)

    @property
    def quote_available(self) -> bool:
        return self.ltp is not None and self.ltp > 0
