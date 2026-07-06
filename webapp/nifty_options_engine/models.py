from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class OptionQuote:
    tradingsymbol: str
    exchange: str = "NFO"
    expiry: date | None = None
    strike: float = 0.0
    option_type: str = ""
    ltp: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    delta: float | None = None
    iv: float | None = None
    oi: int | None = None
    volume: int | None = None


@dataclass
class SpreadLeg:
    tradingsymbol: str
    option_type: str
    strike: float
    expiry: date | None
    transaction_type: str
    quantity: int
    price: float
    ltp: float = 0.0
    delta: float | None = None
    is_short: bool = False
    is_hedge: bool = False


@dataclass
class NiftySpreadStrategy:
    strategy_id: str
    selected_strategy: str
    entry_datetime: datetime | None
    expiry_date: date | None
    spot: float
    market_regime: str
    legs: list[SpreadLeg] = field(default_factory=list)
    net_credit_points: float = 0.0
    spread_width_points: float = 0.0
    max_gain: float = 0.0
    max_loss: float = 0.0
    margin_required: float = 0.0
    credit_pct_of_spread_width: float = 0.0
    confidence_score: int = 0
    risk_status: str = "UNKNOWN"
    warnings: list[str] = field(default_factory=list)
    skip_reason: str = ""


@dataclass
class OrderIntent:
    strategy_id: str
    exchange: str
    tradingsymbol: str
    quantity: int
    transaction_type: str
    product: str
    order_type: str
    price: float
    validity: str
    tag: str = "NIFTY_TACTICAL"
    dry_run: bool = True

    def kite_csv_row(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange,
            "tradingsymbol": self.tradingsymbol,
            "quantity": self.quantity,
            "transaction_type": self.transaction_type,
            "product": self.product,
            "order_type": self.order_type,
            "price": self.price,
            "validity": self.validity,
        }
