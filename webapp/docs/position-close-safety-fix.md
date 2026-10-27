# Position close correction — 2026-10-27

- Found legacy build_buy_order always sets BUY. Webapp now binds closing side to signed position before repricing: short BUY, long SELL. Existing side-specific closes are skipped.
- Shared execution boundary re-fetches broker net positions, checks exchange/symbol/product, side and remaining quantity, and rejects unresolved contract orders. Both scheduler jobs/manual callers share an in-process lock. Broker/external-process races cannot be eliminated by that lock; broker order reconciliation remains required.
- Normal stock prices use BUY discount below min(CMP, average), SELL markup above max(CMP, average). NIFTY retains its separately configured CMP percentages. Emergency exits retain existing rules. Profit target prices do not guarantee fills or net profit.
- Missing fresh prices block preview instead of retaining a legacy BUY-derived price on long closes. STOP OPTION SELL and protected-pair ownership guards remain.
- Position displays the same saved times/interval as Kite Setup. Schedule saves effective today; already-attempted daily jobs do not repeat.
- No live orders or runtime configuration/database edits performed. Runtime DB was already modified and preserved.
