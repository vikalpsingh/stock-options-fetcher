from __future__ import annotations

import html
from datetime import date
from pathlib import Path

from ..models.evaluation_output import EvaluationOutput


def render_html_report(evaluation: EvaluationOutput) -> str:
    risk_items = "".join(f"<li>{html.escape(item)}</li>" for item in evaluation.key_risks) or "<li>None recorded</li>"
    missing_items = "".join(f"<li>{html.escape(item)}</li>" for item in evaluation.missing_fields) or "<li>None</li>"
    score_cards = "".join(
        f"<article><span>{html.escape(name.replace('_', ' ').title())}</span><strong>{score:.1f}</strong></article>"
        for name, score in evaluation.score_breakdown.items()
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>IPO Evaluation</title>
<style>body{{font:15px system-ui;margin:32px;color:#172033}}main{{max-width:1100px;margin:auto}}
.badge{{display:inline-block;padding:8px 12px;border-radius:999px;background:#e2e8f0;font-weight:700}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}}
article,section{{border:1px solid #dbe3ee;border-radius:12px;padding:16px;margin:12px 0}}
article span,article strong{{display:block}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ddd;padding:8px}}</style>
</head><body><main><h1>{html.escape(evaluation.company_name)} ({html.escape(evaluation.symbol)})</h1>
<p class="badge">{html.escape(evaluation.final_decision.value)}</p>
<p>Research date: {evaluation.research_date.isoformat()} | Confidence: {evaluation.decision_confidence:.1f}%</p>
<div class="grid">{score_cards}</div>
<section><h2>Decision</h2><p>Python: {evaluation.python_provisional_decision.value}; GPT: {evaluation.gpt_proposed_decision.value if evaluation.gpt_proposed_decision else 'Not run'}; Final: {evaluation.final_decision.value}</p>
<p>Action: {evaluation.action_detail.value}; maximum allocation {evaluation.maximum_allocation_pct:.2f}% using LIMIT orders only.</p></section>
<section><h2>Valuation and buy zone</h2><pre>{html.escape(evaluation.buy_zone.model_dump_json(indent=2))}</pre></section>
<section><h2>Risks</h2><ul>{risk_items}</ul></section>
<section><h2>Missing evidence</h2><ul>{missing_items}</ul></section>
<section><h2>Monitoring triggers</h2><p>Upgrade: {html.escape('; '.join(evaluation.upgrade_triggers))}</p><p>Downgrade: {html.escape('; '.join(evaluation.downgrade_triggers))}</p></section>
<section><h2>Methodology disclaimer</h2><p>Decision support only. Verify filings, liquidity and valuation before investing. Missing evidence is never interpreted as zero.</p></section>
</main></body></html>"""


def save_html_report(
    evaluation: EvaluationOutput,
    base_dir: str | Path,
    symbols_key: str | None = None,
) -> Path:
    output_dir = Path(base_dir) / "research_store" / "ipo_evaluations" / "html"
    output_dir.mkdir(parents=True, exist_ok=True)
    safe_key = "".join(char for char in (symbols_key or evaluation.symbol).upper() if char.isalnum() or char in "_-")
    path = output_dir / f"{date.today().strftime('%Y%m%d')}_{safe_key or 'IPO'}.html"
    path.write_text(render_html_report(evaluation), encoding="utf-8")
    return path
