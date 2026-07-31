from __future__ import annotations

import json
from typing import Any


PROMPT_VERSION = "1.0"
SYSTEM_INSTRUCTIONS = """You are a seasoned Indian equity research analyst and long-term value investor.
Use only the structured evidence provided. Never invent or estimate missing facts.
Price appreciation is not proof of business quality. Missing governance data is not GREEN.
Respect python_evaluation.provisional_decision and maximum_allowed_decision.
You may downgrade a decision, but may never upgrade it. Return strict JSON only."""


def build_prompt(evidence_package: dict[str, Any]) -> str:
    return (
        f"Prompt version: {PROMPT_VERSION}\n"
        "Evaluate sector runway, business quality, growth, profitability, capital efficiency, "
        "cash flow, working capital, valuation, governance, liquidity, peers, risks and triggers.\n"
        f"Evidence JSON:\n{json.dumps(evidence_package, sort_keys=True, default=str)}"
    )
