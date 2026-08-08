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


# Option liquidity depth gates ---------------------------------------------

# Overall orders = total order count from available bid + ask depth.
LIQUIDITY_AMBER_MIN_TOTAL_ORDERS = 20

# Legacy per-side fields are kept for compatibility; the active gate uses
# LIQUIDITY_AMBER_MIN_TOTAL_ORDERS so far-OTM/monthly options are not blocked
# only because one side of depth is sparse.
LIQUIDITY_AMBER_MIN_BUY_ORDERS = 20

LIQUIDITY_AMBER_MIN_SELL_ORDERS = 20

# Trade activity = actual number_of_trades if available; otherwise Kite volume proxy.
LIQUIDITY_AMBER_MIN_TRADE_ACTIVITY = 100

# Buy orders = sum of order count from top 5 bid depth.
LIQUIDITY_GREEN_MIN_BUY_ORDERS = 1000

# Sell orders = sum of order count from top 5 ask depth.
LIQUIDITY_GREEN_MIN_SELL_ORDERS = 1000

# Trade activity = actual number_of_trades if available; otherwise Kite volume proxy.
LIQUIDITY_GREEN_MIN_TRADE_ACTIVITY = 1000

BLOCK_RED_LIQUIDITY = True
ALLOW_AMBER_LIQUIDITY = True
ALLOW_GREEN_LIQUIDITY = True


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


# Kite/DHAN paired spread expiry-comparison settings -----------------------

# Minimum expected credit/gain required before a paired spread is useful.
# Below this amount, the app evaluates next-month expiry instead of forcing a
# low-premium current-month trade.
MIN_PAIR_MAX_GAIN_INR = 5_000

# Trigger level for automatic next-month comparison when current-month spread
# premium is not meaningful enough for the risk being taken.
AUTO_CHECK_NEXT_EXPIRY_IF_GAIN_BELOW = 5_000

# Allow the DHAN spread evaluator to compare the current monthly expiry with
# next monthly expiry when the current-month max gain is below threshold.
ALLOW_NEXT_MONTH_ROLLOVER_ANALYSIS = True

# Minimum return on defined max risk required for a spread recommendation.
MIN_RETURN_ON_RISK_PCT = 8

# Maximum acceptable defined loss for one paired stock-option spread.
MAX_ACCEPTABLE_PAIR_LOSS_INR = 50_000

# Minimum probability of profit required before recommending a spread.
MIN_POP_FOR_SPREAD = 70

# DHAN-IT call-spread 50/200 DMA watch settings ---------------------------

# Need a full 200 completed daily closes before the DMA gate is trusted.
DHAN_IT_MIN_DMA_HISTORY_SESSIONS = 200

# A stock this far below 50 DMA can bounce sharply; allow review but require
# explicit confirmation instead of treating it as a clean green setup.
DHAN_IT_REBOUND_RISK_BELOW_50DMA_PCT = 8.0

# DHAN-IT sell-on-rise Bear Call Spread signal settings --------------------
DHAN_IT_WATCH_RISE_PCT = 3.0
DHAN_IT_RESISTANCE_PROXIMITY_PCT = 1.0
DHAN_IT_MIN_REJECTION_CONDITIONS = 2
DHAN_IT_UPPER_WICK_MIN_PCT = 40.0
DHAN_IT_SHORT_CE_DELTA_MIN = 0.15
DHAN_IT_SHORT_CE_DELTA_MAX = 0.22
DHAN_IT_HEDGE_CE_DELTA_MIN = 0.05
DHAN_IT_HEDGE_CE_DELTA_MAX = 0.10
DHAN_IT_SHORT_MIN_ATR_DISTANCE = 1.0
DHAN_IT_SHORT_PREFERRED_ATR_DISTANCE = 1.5
DHAN_IT_MIN_POP = 70.0
DHAN_IT_MIN_RETURN_ON_RISK_PCT = 8.0
DHAN_IT_MIN_PAIR_MAX_GAIN_INR = 2_000
DHAN_IT_MAX_ACCEPTABLE_PAIR_LOSS_INR = 40_000
DHAN_IT_QUALITY_OVERRIDE_MIN_POP = 70.0
DHAN_IT_QUALITY_OVERRIDE_MIN_GAIN_INR = 3_000
DHAN_IT_QUALITY_OVERRIDE_MAX_LOSS_INR = 30_000
DHAN_IT_NEAR_CMP_SHIFT_PCT = 1.0
DHAN_IT_MIN_CREDIT_TO_WIDTH_PCT = 8.0
DHAN_IT_MAX_LOSS_PCT_OF_CAPITAL = 0.30
DHAN_IT_QUOTE_TTL_SECONDS = 30
DHAN_IT_OPPORTUNITY_TTL_MINUTES = 10


# Assignment and bucket controls ------------------------------------------

# Maximum cash assignment value per stock for fresh PE selling.
MAX_ASSIGNMENT_VALUE_PER_STOCK = 600_000


# Open-position portfolio controls -----------------------------------------

# If any current position is already in EXIT_NOW, block new SELL entries.
BLOCK_NEW_SELL_IF_ANY_EXIT_NOW = True

# If this many positions are in WARNING, stop adding new income risk.
OPEN_POSITION_WARNING_BLOCK_COUNT = 2
