#!/usr/bin/env python3
"""
Wheel Trader Strategy v2 (Python Version)
Converts the TradingView Pine Script to standalone Python
For NSE options analysis
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys

# Technical indicators
def ema(data, period):
    """Exponential Moving Average"""
    return data.ewm(span=period, adjust=False).mean()

def atr(high, low, close, period=14):
    """Average True Range"""
    tr1 = high - low
    tr2 = np.abs(high - close.shift())
    tr3 = np.abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()

def rsi(data, period=14):
    """Relative Strength Index"""
    delta = data.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def bollinger_bands(data, period=20, num_std=2.0):
    """Bollinger Bands"""
    sma = data.rolling(window=period).mean()
    std = data.rolling(window=period).std()
    upper = sma + (std * num_std)
    lower = sma - (std * num_std)
    return upper, sma, lower

class WheelTrader:
    def __init__(self, df, symbol, tier="TIER_B", signal_mode="BALANCED", has_shares=False, cash_secured=True):
        """
        Initialize Wheel Trader
        
        Parameters:
        -----------
        df : DataFrame with OHLCV columns (Open, High, Low, Close, Volume)
        symbol : str, stock ticker
        tier : str, "TIER_A", "TIER_B", or "TIER_C"
        signal_mode : str, "STRICT", "BALANCED", or "AGGRESSIVE"
        has_shares : bool, whether you hold shares of this stock
        cash_secured : bool, whether you have cash for CSP (Covered Sell Put)
        """
        self.df = df.copy()
        self.symbol = symbol
        self.tier = tier
        self.signal_mode = signal_mode
        self.has_shares = has_shares
        self.cash_secured = cash_secured
        
        # Technical parameters
        self.ema_fast_len = 20
        self.ema_slow_len = 200
        self.atr_len = 14
        self.rsi_len = 14
        self.bb_len = 20
        self.bb_mult = 2.0
        
        # Tier rules
        self.tier_params = {
            "TIER_A": {
                "pct_short": 0.07,
                "pct_long": 0.12,
                "rsi_os": 38,
                "rsi_ob": 70,
                "min_atr_pct": 1.20
            },
            "TIER_B": {
                "pct_short": 0.08,
                "pct_long": 0.12,
                "rsi_os": 35,
                "rsi_ob": 72,
                "min_atr_pct": 1.40
            },
            "TIER_C": {
                "pct_short": 0.12,
                "pct_long": 0.18,
                "rsi_os": 30,
                "rsi_ob": 75,
                "min_atr_pct": 2.20
            }
        }
        
        # Mode relaxations
        self.mode_params = {
            "STRICT": {"yield_factor": 1.0, "rsi_relax": 0},
            "BALANCED": {"yield_factor": 0.75, "rsi_relax": 3},
            "AGGRESSIVE": {"yield_factor": 0.60, "rsi_relax": 5}
        }
        
        # Strategy parameters
        self.short_dte = 10  # trading days
        self.long_dte = 30
        self.strike_step = 5.0
        self.base_atr_mult = 1.5
        self.use_atr_guard = True
        
        self.swing_len = 10
        self.slope_lookback = 5
        self.knife_thresh = -0.7
        
        self.use_snapback = True
        
    def calculate_indicators(self):
        """Calculate all technical indicators"""
        df = self.df
        
        # EMAs
        df['ema_fast'] = ema(df['Close'], self.ema_fast_len)
        df['ema_slow'] = ema(df['Close'], self.ema_slow_len)
        
        # ATR
        df['atr'] = atr(df['High'], df['Low'], df['Close'], self.atr_len)
        
        # RSI
        df['rsi'] = rsi(df['Close'], self.rsi_len)
        
        # Bollinger Bands
        df['bb_upper'], df['bb_basis'], df['bb_lower'] = bollinger_bands(
            df['Close'], self.bb_len, self.bb_mult
        )
        
        # ATR %
        df['atr_pct'] = (df['atr'] / df['Close']) * 100.0
        df['atr_pct_smooth'] = df['atr_pct'].rolling(window=5).mean()
        
        return df
    
    def calculate_signals(self):
        """Calculate trading signals"""
        df = self.calculate_indicators()
        
        # Get tier parameters
        tier_params = self.tier_params[self.tier]
        mode_params = self.mode_params[self.signal_mode]
        
        # Get adjusted parameters
        yield_factor = mode_params['yield_factor']
        rsi_relax = mode_params['rsi_relax']
        
        min_atr_pct_adj = tier_params['min_atr_pct'] * yield_factor
        rsi_ob_adj = max(50, tier_params['rsi_ob'] - rsi_relax)
        rsi_os_adj = min(50, tier_params['rsi_os'] + rsi_relax)
        
        knife_thresh_adj = self.knife_thresh * (1.25 if self.signal_mode == "BALANCED" else 1.50 if self.signal_mode == "AGGRESSIVE" else 1.0)
        
        trend_buf = 0.97 if self.signal_mode == "AGGRESSIVE" else 0.99 if self.signal_mode == "BALANCED" else 1.00
        
        # Rubber Band setup
        df['touch_upper'] = df['High'] >= df['bb_upper']
        df['touch_lower'] = df['Low'] <= df['bb_lower']
        
        if self.use_snapback:
            df['rb_call_ok'] = df['touch_upper'] & (df['Close'] < df['bb_upper'])
            df['rb_put_ok'] = df['touch_lower'] & (df['Close'] > df['bb_lower'])
        else:
            df['rb_call_ok'] = df['touch_upper']
            df['rb_put_ok'] = df['touch_lower']
        
        # Falling knife (EMA slope)
        df['ema_slope'] = (df['ema_fast'] - df['ema_fast'].shift(self.slope_lookback)) / df['atr'].fillna(1)
        df['is_falling_knife'] = df['ema_slope'] < knife_thresh_adj
        
        # Breakdown (swing low)
        df['swing_low'] = df['Low'].rolling(window=self.swing_len).min().shift(1)
        df['breakdown'] = (df['Close'] < df['swing_low']) & ((df['High'] - df['Low']) > 1.2 * df['atr'])
        
        # Trend guard for PUT
        df['trend_ok_for_put'] = df['Close'] > df['ema_slow'] * trend_buf
        
        # Yield gate
        df['yield_ok'] = df['atr_pct_smooth'] >= min_atr_pct_adj
        df['yield_low'] = ~df['yield_ok']
        
        # Setup logic
        if self.signal_mode == "STRICT":
            df['call_setup'] = self.has_shares & df['rb_call_ok'] & (df['rsi'] >= rsi_ob_adj)
            df['put_setup'] = self.cash_secured & df['trend_ok_for_put'] & df['rb_put_ok'] & (df['rsi'] <= rsi_os_adj)
            
            df['call_blocked'] = df['yield_low'] | df['is_falling_knife'] | df['breakdown']
            df['put_blocked'] = df['yield_low'] | df['is_falling_knife'] | df['breakdown']
            
        elif self.signal_mode == "BALANCED":
            df['call_setup'] = self.has_shares & (df['rsi'] >= rsi_ob_adj) & (df['rb_call_ok'] | (df['Close'] > df['bb_basis']))
            df['put_setup'] = self.cash_secured & df['trend_ok_for_put'] & (df['rsi'] <= rsi_os_adj) & (df['rb_put_ok'] | (df['Close'] < df['bb_basis']))
            
            df['call_blocked'] = df['yield_low'] | df['is_falling_knife']
            df['put_blocked'] = df['yield_low'] | df['is_falling_knife']
            
        else:  # AGGRESSIVE
            df['call_setup'] = self.has_shares & ((df['rsi'] >= rsi_ob_adj) | df['rb_call_ok'])
            df['put_setup'] = self.cash_secured & df['trend_ok_for_put'] & ((df['rsi'] <= rsi_os_adj) | df['rb_put_ok'])
            
            df['call_blocked'] = False
            df['put_blocked'] = df['is_falling_knife']
        
        # Final signals
        df['sell_call_now'] = df['call_setup'] & ~df['call_blocked']
        df['sell_put_now'] = df['put_setup'] & ~df['put_blocked']
        
        # Signal priority
        df['signal'] = "WAIT"
        df.loc[df['sell_put_now'] & ~self.has_shares, 'signal'] = "SELL PUT NOW"
        df.loc[df['sell_call_now'], 'signal'] = "SELL CALL NOW"
        df.loc[(df['sell_put_now'] & ~df['sell_call_now']) | (~self.has_shares & df['sell_put_now']), 'signal'] = "SELL PUT NOW"
        
        # Strike targets
        df['pct_otm'] = tier_params['pct_short']  # Simplified for last row
        
        if self.use_atr_guard:
            dist_pct = df['Close'] * df['pct_otm']
            dist_atr = df['atr'] * self.base_atr_mult
            dist_final = np.maximum(dist_pct, dist_atr)
        else:
            dist_final = df['Close'] * df['pct_otm']
        
        df['put_strike'] = np.floor(df['Close'] - dist_final / self.strike_step) * self.strike_step
        df['call_strike'] = np.ceil(df['Close'] + dist_final / self.strike_step) * self.strike_step
        
        self.df = df
        return df
    
    def get_latest_signal(self):
        """Get the latest signal"""
        if len(self.df) == 0:
            return None
        
        row = self.df.iloc[-1]
        
        return {
            'date': row.name if hasattr(row.name, 'strftime') else 'N/A',
            'close': row['Close'],
            'signal': row['signal'],
            'put_strike': row['put_strike'],
            'call_strike': row['call_strike'],
            'rsi': row['rsi'],
            'atr_pct': row['atr_pct_smooth'],
            'trend_ok': row['trend_ok_for_put'],
            'yield_ok': row['yield_ok'],
            'rb_call': row['rb_call_ok'],
            'rb_put': row['rb_put_ok'],
            'falling_knife': row['is_falling_knife'],
            'breakdown': row['breakdown']
        }


def create_sample_data(symbol, days=100):
    """Create sample OHLCV data for testing"""
    dates = pd.date_range(end=datetime.now(), periods=days, freq='D')
    
    # Generate realistic OHLCV
    np.random.seed(42)
    close = np.cumsum(np.random.randn(days) * 10 + 100) + 1000
    
    data = pd.DataFrame({
        'Date': dates,
        'Open': close + np.random.randn(days) * 5,
        'High': close + np.abs(np.random.randn(days) * 15),
        'Low': close - np.abs(np.random.randn(days) * 15),
        'Close': close,
        'Volume': np.random.randint(100000, 1000000, days)
    })
    
    data.set_index('Date', inplace=True)
    return data


def main():
    print("=" * 80)
    print("WHEEL TRADER STRATEGY v2 (Python)")
    print("=" * 80)
    print()
    
    # Try to load real data
    csv_files = ['input.csv', 'stocks.csv', 'Sep_2025_options.csv']
    df = None
    
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file, index_col='Date', parse_dates=True)
            if 'Close' in df.columns:
                print(f"✓ Loaded data from {csv_file}")
                break
        except FileNotFoundError:
            continue
    
    # If no real data, use sample
    if df is None:
        print("⚠ No CSV data found. Using sample data...")
        df = create_sample_data('SAMPLE', days=100)
        symbol = 'SAMPLE'
    else:
        # Normalize column names
        df.columns = [col.capitalize() if col.lower() in ['open', 'high', 'low', 'close', 'volume'] else col for col in df.columns]
        symbol = 'NSE_STOCK'
    
    print(f"Data shape: {df.shape}")
    print(f"Date range: {df.index[0]} to {df.index[-1]}")
    print()
    
    # Test different configurations
    configs = [
        ("TIER_A", "STRICT", False, True),
        ("TIER_B", "BALANCED", False, True),
        ("TIER_C", "AGGRESSIVE", False, True),
    ]
    
    for tier, mode, has_shares, cash_secured in configs:
        print("-" * 80)
        print(f"Testing: {tier} | {mode} | Shares: {has_shares} | Cash: {cash_secured}")
        print("-" * 80)
        
        try:
            trader = WheelTrader(df, symbol, tier=tier, signal_mode=mode, 
                               has_shares=has_shares, cash_secured=cash_secured)
            trader.calculate_signals()
            
            signal = trader.get_latest_signal()
            
            if signal:
                print(f"Date: {signal['date']}")
                print(f"Close: {signal['close']:.2f}")
                print(f"Signal: {signal['signal']:15} | RSI: {signal['rsi']:6.1f} | ATR%: {signal['atr_pct']:6.2f}%")
                print(f"PUT Strike: {signal['put_strike']:8.0f} | CALL Strike: {signal['call_strike']:8.0f}")
                print(f"Filters - Trend: {signal['trend_ok']:5} | Yield: {signal['yield_ok']:5} | RB-C: {signal['rb_call']:5} | RB-P: {signal['rb_put']:5}")
                print(f"Blockers - Knife: {signal['falling_knife']:5} | Breakdown: {signal['breakdown']:5}")
                print()
        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            print()
    
    print("=" * 80)
    print("✓ Wheel Trader Analysis Complete")
    print("=" * 80)


if __name__ == "__main__":
    main()
