from __future__ import annotations

from ..models.evaluation_output import EvaluationOutput


def data_issues(evaluation: EvaluationOutput) -> list[str]:
    return list(dict.fromkeys([*evaluation.missing_fields, *evaluation.hard_rule_blocks]))
