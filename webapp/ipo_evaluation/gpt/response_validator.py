from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from ..analytics.decision_engine import DECISION_RANK
from ..models.evaluation_output import Decision, EvaluationOutput
from .response_schema import GptEvaluationResponse


class GptResponseValidationError(ValueError):
    pass


def validate_gpt_response(
    payload: str | bytes | dict[str, Any],
    python_evaluation: EvaluationOutput,
) -> GptEvaluationResponse:
    try:
        response = (
            GptEvaluationResponse.model_validate_json(payload)
            if isinstance(payload, (str, bytes))
            else GptEvaluationResponse.model_validate(payload)
        )
    except ValidationError as exc:
        raise GptResponseValidationError(f"FAILED_SCHEMA_VALIDATION: {exc}") from exc
    if DECISION_RANK[response.decision] > DECISION_RANK[python_evaluation.maximum_allowed_decision]:
        raise GptResponseValidationError("GPT decision exceeds maximum_allowed_decision")
    if response.decision == Decision.BUY and (
        python_evaluation.hard_rule_blocks or python_evaluation.buy_zone.status != "CALCULATED"
    ):
        raise GptResponseValidationError("BUY is invalid with hard blocks or missing valuation")
    if response.decision == Decision.DATA_INSUFFICIENT and not response.missing_evidence:
        raise GptResponseValidationError("DATA_INSUFFICIENT requires missing_evidence")
    return response
