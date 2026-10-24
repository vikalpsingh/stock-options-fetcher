# Usage tracking

Disabled by default. Configure deployment environment (do not put secrets here):

```
USAGE_TRACKING_ENABLED=true
USAGE_TRACKING_LEVEL=ENTRYPOINTS
USAGE_TRACKING_SAMPLE_RATE=0.1
USAGE_TRACKING_LOG_DIR=<absolute runtime directory>
USAGE_TRACKING_ENVIRONMENT=PROD
DEPLOYMENT_GIT_SHA=<deployed commit>
```

Entry boundaries always sampled at 1; optional noncritical functions are sampled only at ALL level. HTTP handler instrumentation deliberately records method only, never raw URLs/query strings or account IDs. Selected execution, NIFTY, broker, scheduler and GPT-generation boundaries are instrumented; other modules are unknown coverage. MODULE_LOADED is lazy first use, not import-time evidence.

A bounded 2048-event queue feeds a daemon writer. Full queues drop events; logging errors do not affect the caller. No arguments, results, exception messages, tokens or financial values are recorded. Function outcomes are SUCCESS/FAILURE. Rotation retains the active 5 MB file plus five archives (approximately 30 MB per process). Use a separate directory per worker process; rotation is not multi-process coordinated. Abrupt shutdown can lose buffered events. This is evidence gathering, not an audit ledger.

Export only usage JSONL files via your existing secure administration channel, not order logs/settings. Restrict directory permissions. Retention must cover at least 30–60 days of relevant activity; rotations may require periodic secure exports. Rare recovery/expiry flows need longer. No automatic archival.

```
python -m observability.inventory
python -m observability.report --input <exported-log-directory> --output <report-directory>
```

No production observations have been collected by this implementation. Possible unused functions/imports are review candidates only. Archival requires an evidence proposal, explicit human approval, preserved Git history, focused regression checks and rollback to the prior deployment SHA. Runtime and protected code is never removed by these tools.
