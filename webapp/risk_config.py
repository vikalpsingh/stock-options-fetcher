"""Central trading risk settings for Income Desk.

Edit this file when risk appetite changes.  Keep the names stable so the app,
tests, and reports can all read the same trading rules.
"""

# General risk settings -----------------------------------------------------

# Stop opening new option income trades if monthly realized option loss crosses
# this percent of the option capital allocated to the strategy.
MAX_OPTION_LOSS_PER_MONTH_PCT = 1.0

# Maximum loss allowed on one trade as a percent of total option capital.
MAX_LOSS_PER_TRADE_PCT_OF_CAPITAL = 0.30

# Maximum new positions the app should approve in one trading day.
MAX_POSITIONS_PER_DAY = 5

# Header-only CSV is a valid "NO TRADE DAY" output.
ALLOW_EMPTY_CSV = True

# Every SELL option must have a target, warning level, and hard stop.
BLOCK_ORDER_IF_STOPLOSS_MISSING = True

# Approximate option capital used for portfolio-level monthly-loss controls.
# Override from app data later when live capital accounting is available.
OPTION_CAPITAL_DEPLOYED = 1_000_000.0


# Covered Call / CE sell settings -----------------------------------------

# Book covered CALL profit after this percent of premium has decayed.
CE_PROFIT_BOOKING_PCT = 50

# Warning when sold CE premium reaches entry premium x this value.
CE_WARNING_MULTIPLIER = 2.0

# Hard exit when sold CE premium reaches entry premium x this value.
CE_HARD_EXIT_MULTIPLIER = 3.0

# Minimum CE premium yield needed to justify capping upside.
CE_MIN_PREMIUM_YIELD_PCT = 0.60

# Avoid CE selling when stock is this close to breakout/highs.
CE_AVOID_IF_STOCK_NEAR_BREAKOUT_PCT = 3.0

# Avoid CE selling when stock momentum is too strong.
CE_AVOID_IF_RSI_ABOVE = 65

# Avoid aggressive CE selling when Nifty is in a strong uptrend.
CE_AVOID_IF_NIFTY_STRONG_UPTREND = True


# Cash Secured Put / PE sell settings --------------------------------------

# Book PE profit after this percent of premium has decayed.
PE_PROFIT_BOOKING_PCT = 75

# Warning when sold PE premium reaches entry premium x this value.
PE_WARNING_MULTIPLIER = 2.0

# Hard exit when sold PE premium reaches entry premium x this value.
PE_HARD_EXIT_MULTIPLIER = 3.0

# Minimum PE premium yield needed for cash-secured assignment risk.
PE_MIN_PREMIUM_YIELD_PCT = 0.75

# Avoid PE selling below short trend support.
PE_AVOID_IF_STOCK_BELOW_EMA20 = True

# Avoid PE selling below swing trend support.
PE_AVOID_IF_STOCK_BELOW_EMA50 = True

# Avoid PE selling when breakdown volume is heavy.
PE_AVOID_IF_HIGH_SELL_VOLUME = True


# Market regime settings ---------------------------------------------------

# Above this VIX, reduce fresh position size.
VIX_REDUCE_SIZE_ABOVE = 15

# Above this VIX, block fresh income trades.
VIX_BLOCK_NEW_TRADES_ABOVE = 20

# Reduce fresh size if VIX expands this much in five sessions.
VIX_5D_EXPANSION_REDUCE_PCT = 12

# Block fresh trades if VIX expansion is this large.
VIX_5D_EXPANSION_BLOCK_PCT = 25


# Event-risk settings ------------------------------------------------------

# Block new option selling if event is inside this many trading days.
BLOCK_IF_EVENT_WITHIN_TRADING_DAYS = 5

# Event types that can gap the stock and invalidate premium math.
EVENT_TYPES_TO_BLOCK = [
    "earnings",
    "results",
    "board_meeting",
    "dividend",
    "split",
    "bonus",
    "merger",
    "demerger",
]


# Expiry-risk settings -----------------------------------------------------

# Existing positions should be closed or rolled before this many expiry days.
EXIT_BEFORE_EXPIRY_DAYS = 4

# Do not open new income trades inside this many days to expiry.
BLOCK_NEW_TRADES_IF_DAYS_TO_EXPIRY_LESS_THAN = 5


# Assignment and bucket controls ------------------------------------------

# Maximum cash assignment value per stock for fresh PE selling.
MAX_ASSIGNMENT_VALUE_PER_STOCK = 600_000


# Open-position portfolio controls -----------------------------------------

# If any current position is already in EXIT_NOW, block new SELL entries.
BLOCK_NEW_SELL_IF_ANY_EXIT_NOW = True

# If this many positions are in WARNING, stop adding new income risk.
OPEN_POSITION_WARNING_BLOCK_COUNT = 2
