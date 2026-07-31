from __future__ import annotations

from typing import Any

from ..models.evaluation_output import EvaluationOutput
from ..service import evaluation_fields


def comparison_row(evaluation: EvaluationOutput) -> dict[str, Any]:
    return {
        "company": evaluation.company_name,
        "symbol": evaluation.symbol,
        **evaluation_fields(evaluation),
        "research_date": evaluation.research_date.isoformat(),
    }
