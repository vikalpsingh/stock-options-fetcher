# Architecture changelog

2026-10-24: extracted completed_order_current_pnl into position_order_display.py with app.py import facade. No formula/signature changes. Comparable LF-normalized UTF-8 size before extraction/instrumentation: 2,599,210 bytes; after: 2,598,975 bytes. Physical file size includes Windows line endings. Other execution changes predate this extraction. New dependency: app -> position_order_display (math, typing only).
Instrumentation imports observability.usage_tracker; no app imports or broker/database initialization. No archived functions.
