# Code architecture
Generated with AST only; no application imports.
Static names/callers are approximate; dynamic routing, callbacks and reflection require review. No classification authorises deletion.
## Largest production modules
- app.py: 2,650,484 bytes; 973 definitions
- test_pe_sell_strategy.py: 175,051 bytes; 227 definitions
- ipo_data_service.py: 161,090 bytes; 114 definitions
- nifty_grow.py: 72,968 bytes; 47 definitions
- nifty_options_engine\ui.py: 59,353 bytes; 16 definitions
- sell_on_rise_monitor.py: 55,579 bytes; 50 definitions
- fifty_two_week_ai_call_spread.py: 49,979 bytes; 59 definitions
- ipo\research.py: 35,636 bytes; 36 definitions
- trade_protected_execution.py: 33,405 bytes; 25 definitions
- sector_income.py: 33,116 bytes; 27 definitions
- ipo_screener_engine.py: 32,493 bytes; 31 definitions
- kite_spread_repository.py: 27,597 bytes; 26 definitions
- pnl_service.py: 27,256 bytes; 33 definitions
- value_stock\pdf_parser.py: 26,613 bytes; 33 definitions
- risk_engine.py: 25,014 bytes; 17 definitions
- monthly_risk_control.py: 24,680 bytes; 26 definitions
- dhan_it_call_watch.py: 21,960 bytes; 16 definitions
- nifty_tactical.py: 20,415 bytes; 17 definitions
- value_stock\repository.py: 20,032 bytes; 19 definitions
- dhan_it_pair_execution.py: 19,932 bytes; 19 definitions
- kite_spread_evaluator.py: 18,992 bytes; 14 definitions
- nifty_options_engine\ticket.py: 18,952 bytes; 11 definitions
- nifty_options_engine\workflow.py: 17,552 bytes; 10 definitions
- ipo\symbol_resolution\symbol_resolver.py: 16,892 bytes; 18 definitions
- nifty_options_engine\service.py: 15,683 bytes; 6 definitions
- nifty_options_engine\reconciliation.py: 14,504 bytes; 9 definitions
- dhan_fno_top10_engine.py: 13,922 bytes; 12 definitions
- kite_pnl_importer.py: 13,721 bytes; 12 definitions
- kite_spread_engine.py: 13,518 bytes; 6 definitions
- fii_sector_pdf_parser.py: 13,334 bytes; 20 definitions
## Detailed map
See architecture_inventory.json for every qualified definition, line, complexity, classification, possible calls, imports and route string. Route strings are candidates, not proof of registration.
## Boundaries
Order/broker/risk/authentication/reconciliation/expiry/scheduler functions are protected. SQLite, Kite/DHAN and dynamic imports are exposed through the import and call indexes. Never import app.py for inventory.
## Extraction priorities
Extract pure renderers and formatters first. Keep existing nifty_options_engine and broker adapters; do not create duplicate engines. Closures and app-global dependencies need explicit dependency injection before extraction.
## Duplicate review
Matching short names or call patterns are candidates only. Different financial meanings must not be merged automatically.