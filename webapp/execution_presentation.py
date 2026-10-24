"""Shared execution presentation and estimate policy; no broker side effects."""
import html
import math


def margin_estimate_status(required, available, *, defined_risk=False, paper=False, verified_insufficient=False):
    """Only local estimate failures become advisory; verified broker insufficiency stays blocked."""
    if verified_insufficient:
        return "BLOCK"
    valid = all(isinstance(v, (int, float)) and math.isfinite(v) for v in (required, available))
    if valid and required > 0 and available >= required:
        return "PASS"
    return "WARNING" if defined_risk or paper else "BLOCK"


def render_discipline_cards():
    cards = (
        ("amber", "◎", "Emotional Discipline", "Trade Without Fear or Overconfidence",
         "Accept the risk before entering. Neither fear nor recent profits should control the next decision."),
        ("blue", "◈", "Market Perspective", "The Market Has Its Own Perspective",
         "The market does not need to agree with my analysis. Follow price action and accept contradictory evidence."),
        ("teal", "↗", "Opportunity Mindset", "Always Focus on the Next Opportunity",
         "Do not defend a losing position or chase missed profits. Preserve capital for the next valid setup."),
        ("violet", "◇", "Enter the Zone", "The Market Is Always Uncertain — Anything Is Possible",
         "No single outcome is guaranteed. Define maximum risk, follow the plan and accept uncertainty."),
    )
    css = """<style>.execution-discipline{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:12px 0}.execution-discipline .discipline-card{margin:0;padding:12px 14px;border:1px solid var(--edge);border-left:4px solid var(--tone);border-radius:10px;background:var(--soft);min-width:0}.discipline-card.amber{--tone:#92400e;--edge:#fcd34d;--soft:#fffbeb}.discipline-card.blue{--tone:#1e40af;--edge:#93c5fd;--soft:#eff6ff}.discipline-card.teal{--tone:#115e59;--edge:#5eead4;--soft:#f0fdfa}.discipline-card.violet{--tone:#5b21b6;--edge:#c4b5fd;--soft:#f5f3ff}.execution-discipline small{color:var(--tone);font-weight:700}.execution-discipline h3{color:#17202a;font-size:15px;margin:5px 0}.execution-discipline p{color:#334155;font-size:12px;line-height:1.45;margin:0}@media(max-width:600px){.execution-discipline{grid-template-columns:minmax(0,1fr)}}</style>"""
    return css+'<div class="execution-discipline" aria-label="Trading discipline">'+''.join(
        '<article class="discipline-card '+tone+'"><small><span aria-hidden="true">'+icon+'</span> '+html.escape(label)+'</small><h3>'+html.escape(title)+'</h3><p>'+html.escape(body)+'</p></article>'
        for tone,icon,label,title,body in cards)+'</div>'
