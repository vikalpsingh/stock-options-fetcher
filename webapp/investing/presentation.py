"""Compact monetary display; sorting must use original rupee values."""
import math

def lakh_amount(value):
    try:
        amount=float(value)
        if not math.isfinite(amount):return 'N/A'
    except (TypeError,ValueError):return 'N/A'
    return f'₹{amount/100000:,.2f} L' if abs(amount)>=1000 else f'₹{amount:,.0f}'
