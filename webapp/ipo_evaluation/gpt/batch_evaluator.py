from __future__ import annotations

import json
import os
from typing import Any, Iterable

from openai import OpenAI

from .prompt_builder import SYSTEM_INSTRUCTIONS, build_prompt
from .response_schema import GptEvaluationResponse


def build_batch_requests(items: Iterable[tuple[str, dict[str, Any]]], model: str | None = None) -> list[dict[str, Any]]:
    selected_model = model or os.getenv("OPENAI_BATCH_MODEL", os.getenv("OPENAI_RESEARCH_MODEL", "gpt-5"))
    schema = GptEvaluationResponse.model_json_schema()
    return [
        {
            "custom_id": custom_id,
            "method": "POST",
            "url": "/v1/responses",
            "body": {
                "model": selected_model,
                "instructions": SYSTEM_INSTRUCTIONS,
                "input": build_prompt(evidence),
                "store": False,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "ipo_evaluation",
                        "strict": True,
                        "schema": schema,
                    }
                },
            },
        }
        for custom_id, evidence in items
    ]


def serialize_batch_jsonl(requests: Iterable[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(request, sort_keys=True) for request in requests) + "\n"


def match_batch_outputs(lines: Iterable[str]) -> dict[str, dict[str, Any]]:
    matched: dict[str, dict[str, Any]] = {}
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        custom_id = str(row.get("custom_id") or "")
        if custom_id:
            matched[custom_id] = row
    return matched


class IpoBatchEvaluator:
    def __init__(self, client: OpenAI | None = None) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if client is None and not api_key:
            raise ValueError("OPENAI_API_KEY is not configured")
        self.client = client or OpenAI(api_key=api_key)

    def submit_jsonl(self, jsonl: str) -> dict[str, str]:
        if not jsonl.strip():
            raise ValueError("No eligible IPO batch requests were prepared")
        uploaded = self.client.files.create(
            file=("ipo_evaluation_batch.jsonl", jsonl.encode("utf-8"), "application/jsonl"),
            purpose="batch",
        )
        batch = self.client.batches.create(
            input_file_id=uploaded.id,
            endpoint="/v1/responses",
            completion_window="24h",
            metadata={"workflow": "ipo_long_term_evaluation"},
        )
        return {
            "batch_job_id": str(batch.id),
            "input_file_id": str(uploaded.id),
            "status": str(getattr(batch, "status", "validating")),
        }

    def status(self, batch_job_id: str) -> dict[str, Any]:
        batch = self.client.batches.retrieve(batch_job_id)
        return batch.model_dump(mode="json") if hasattr(batch, "model_dump") else {"id": batch_job_id}
