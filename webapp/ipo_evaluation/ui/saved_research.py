from __future__ import annotations

from ..storage.repositories import EvaluationRepository


def load_saved_research(company_key: str | None = None) -> list[dict[str, object]]:
    return EvaluationRepository().list_runs(company_key)
