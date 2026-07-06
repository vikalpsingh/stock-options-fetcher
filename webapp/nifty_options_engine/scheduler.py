from __future__ import annotations

NIFTY_ENGINE_JOBS = [
    {"name": "NIFTY preview job", "schedule": "Weekdays 09:20 IST", "purpose": "Refresh regime and tactical spread preview."},
    {"name": "NIFTY entry job", "schedule": "Friday 15:16 IST", "purpose": "Generate tactical entry suggestions by default."},
    {"name": "NIFTY exit monitor", "schedule": "Every 15 min market hours", "purpose": "Monitor profit, stop, emergency and time exits."},
    {"name": "NIFTY force close", "schedule": "Before force-close datetime", "purpose": "Prevent stale NIFTY strategy risk."},
]
