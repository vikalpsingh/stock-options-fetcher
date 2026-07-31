from __future__ import annotations

import html

from ..models.evaluation_output import EvaluationOutput


def render_evaluation_summary(evaluations: list[EvaluationOutput]) -> str:
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(item.company_name)}</td><td>{html.escape(item.symbol)}</td>"
        f"<td>{item.data_quality_score:.0f}</td><td>{item.investment_score:.1f}</td>"
        f"<td>{html.escape(item.python_provisional_decision.value)}</td>"
        f"<td>{html.escape(item.gpt_proposed_decision.value if item.gpt_proposed_decision else 'NOT_RUN')}</td>"
        f"<td>{html.escape(item.final_decision.value)}</td><td>{item.decision_confidence:.1f}%</td>"
        "</tr>"
        for item in evaluations
    )
    return (
        '<section class="panel"><div class="panel-title">Long-Term Evaluation</div>'
        "<table><thead><tr><th>Company</th><th>Symbol</th><th>Data Quality</th>"
        "<th>Investment Score</th><th>Python Decision</th><th>GPT Decision</th>"
        f"<th>Final Decision</th><th>Confidence</th></tr></thead><tbody>{rows}</tbody></table></section>"
    )
