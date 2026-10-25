"""Opt-in data checkpoint facade. Not registered as an HTTP/order route."""
from .config import enabled
from .fundamentals import import_observations


def import_fundamentals(repository, account, content, format, *, environ=None, settings=None):
    if not enabled(environ, settings):
        raise PermissionError('Investing v2 is disabled.')
    observations = import_observations(content, format)
    repository.ensure_schema()
    return repository.import_batch(account, observations)
