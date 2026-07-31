from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable

from openai import OpenAI

from .prompt_builder import SYSTEM_INSTRUCTIONS, build_prompt
from .response_schema import GptEvaluationResponse

LOGGER = logging.getLogger(__name__)


class IpoOpenAIClient:
    def __init__(
        self,
        client: OpenAI | None = None,
        *,
        model: str | None = None,
        timeout: float = 60,
        max_attempts: int = 2,
    ) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if client is None and not api_key:
            raise ValueError("OPENAI_API_KEY is not configured")
        self.client = client or OpenAI(api_key=api_key, timeout=timeout)
        self.model = model or os.getenv("OPENAI_RESEARCH_MODEL", "gpt-5")
        self.max_attempts = max(1, max_attempts)

    def evaluate(self, evidence_package: dict[str, Any]) -> tuple[GptEvaluationResponse, dict[str, Any]]:
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                response = self.client.responses.parse(
                    model=self.model,
                    instructions=SYSTEM_INSTRUCTIONS,
                    input=build_prompt(evidence_package),
                    text_format=GptEvaluationResponse,
                    store=False,
                )
                parsed = response.output_parsed
                if not isinstance(parsed, GptEvaluationResponse):
                    raise ValueError("OpenAI returned no parsed structured output")
                usage = getattr(response, "usage", None)
                metadata = {
                    "request_id": getattr(response, "_request_id", None),
                    "response_id": getattr(response, "id", None),
                    "model": self.model,
                    "usage": usage.model_dump() if hasattr(usage, "model_dump") else {},
                }
                LOGGER.info("IPO OpenAI response id=%s request_id=%s usage=%s", metadata["response_id"], metadata["request_id"], metadata["usage"])
                return parsed, metadata
            except Exception as exc:
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    time.sleep(2**attempt)
        raise RuntimeError(f"OpenAI evaluation failed after {self.max_attempts} attempts") from last_error
