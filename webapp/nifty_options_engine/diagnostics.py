"""User-safe diagnostics: never include exception messages or broker responses."""
import traceback
from pathlib import Path


def loading_error(exc, stage):
    kind = type(exc).__name__
    frames = traceback.extract_tb(exc.__traceback__)
    location = f'{Path(frames[-1].filename).name}:{frames[-1].lineno}' if frames else 'unknown'
    if kind in {'TokenException', 'PermissionException'}:
        advice = 'Reconnect the selected profile in Kite Setup and generate today\'s access token. Check that this Kite app has market-data access.'
    elif kind in {'NetworkException', 'ConnectionError', 'ReadTimeout', 'TimeoutError'}:
        advice = 'Kite could not be reached. Retry Refresh after connectivity is restored.'
    elif kind in {'OperationalError', 'IntegrityError'}:
        advice = 'The local strategy database could not be read or updated. Keep the database intact and report this diagnostic.'
    else:
        advice = 'Loading failed. Report this diagnostic so the failing step can be corrected.'
    return f'{advice} Diagnostic: {stage} / {kind} / {location}. No automatic order retry was made; reconcile any pending execution.'
