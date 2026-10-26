"""Position-only daily movement formatting; unavailable closes stay unavailable."""
import math

def daily_change(cmp, previous_close):
    try:
        price,close=float(cmp),float(previous_close)
        if not all(math.isfinite(x) and x>0 for x in (price,close)):return None
        return (price/close-1)*100
    except (ValueError,TypeError):return None


def movement_html(cmp,previous_close):
    change=daily_change(cmp,previous_close)
    if change is None:return '<span class="signal-neutral">Day change unavailable</span>'
    tone='pnl-positive' if change>0 else 'pnl-negative' if change<0 else 'signal-neutral'
    return f'<span class="{tone}" title="Change from previous trading close">{change:+.2f}% today</span>'
