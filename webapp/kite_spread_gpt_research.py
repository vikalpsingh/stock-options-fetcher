"""GPT advisory parser/prompt for Kite spreads."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.request import Request, urlopen


SYSTEM_PROMPT = """You are a senior Indian F&O option spread selector. Return strict JSON only.
Avoid event risk, illiquid options, CE sells during breakout, and PE sells during breakdown.
GPT is advisory only; final approval is by app risk engine and live Kite data."""


def build_prompt(candidates: list[dict[str, Any]]) -> str:
    return "Suggest CE/PE spread candidates for today from this universe:\n" + json.dumps(candidates, default=str)


def parse_kite_spread_gpt(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end >= start:
        text = text[start : end + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("GPT response must be a JSON object.")
    data.setdefault("market_regime", "NO_TRADE")
    data.setdefault("market_comment", "")
    data.setdefault("candidates", [])
    data.setdefault("no_trade_reason", "")
    clean_candidates = []
    for item in data.get("candidates") or []:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").upper().strip()
        if not symbol:
            continue
        clean_candidates.append({**item, "symbol": symbol})
    data["candidates"] = clean_candidates
    return data


def suggest_stocks_with_openai(candidates: list[dict[str, Any]], model: str = "gpt-4.1-mini", api_key: str | None = None) -> tuple[list[dict[str, Any]], str]:
    key = (api_key or os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        return [], "Missing OPENAI_API_KEY; existing Kite spread watchlist remains usable."
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_prompt(candidates)},
        ],
        "temperature": 0.2,
    }
    req = Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=45) as response:  # nosec - fixed OpenAI endpoint
            body = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        return [], f"Kite spread GPT advisory unavailable: {exc}"
    text = str(body.get("output_text") or "")
    if not text:
        parts: list[str] = []
        for item in body.get("output") or []:
            for content in item.get("content") or []:
                if content.get("type") in {"output_text", "text"}:
                    parts.append(str(content.get("text") or ""))
        text = "\n".join(parts)
    try:
        return list(parse_kite_spread_gpt(text).get("candidates") or []), ""
    except Exception as exc:
        return [], f"Kite spread GPT JSON could not be parsed: {exc}"
