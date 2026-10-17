"""Optional AI assistance via the Claude API (structured outputs).

Enabled only when an API key is configured (env ANTHROPIC_API_KEY or the Settings page).
Only column headers, field names and a few sample values are sent - never the whole file.
"""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel

DEFAULT_MODEL = "claude-opus-5-5"
MAX_SAMPLES = 5


class AiError(RuntimeError):
    pass


class MappingItem(BaseModel):
    field: str
    column: str  # "" when no column fits
    confidence: float
    reason: str


class MappingSuggestion(BaseModel):
    items: list[MappingItem]


class HeaderItem(BaseModel):
    name: str
    value: str


class TemplateDraft(BaseModel):
    method: str
    url: str
    headers: list[HeaderItem]
    body: str  # JSON text using {{field}} / {{field:type}} placeholders, or ""
    notes: str


class FixItem(BaseModel):
    row_index: int
    field: str
    suggested_value: str
    reason: str


class FixSuggestions(BaseModel):
    fixes: list[FixItem]


class FailureGroup(BaseModel):
    cause: str
    count: int
    row_indexes: list[int]
    suggestion: str


class FailureInsights(BaseModel):
    summary: str
    groups: list[FailureGroup]


class ParamItem(BaseModel):
    name: str
    value: str
    location: str  # "auto" (placeholder), "query" or "header"


class RequestDraft(BaseModel):
    method: str
    url: str  # may contain {{placeholders}} for values the user supplies as params
    headers: list[HeaderItem]
    params: list[ParamItem]
    body: str  # JSON text or ""
    notes: str


class KeyValue(BaseModel):
    key: str
    value: str


class ResponseAnalysis(BaseModel):
    outcome: str  # success | client_error | server_error | auth_error | network_error | unknown
    summary: str
    key_points: list[str]
    extracted: list[KeyValue]  # the most useful values in the response (ids, totals, error codes...)
    suggested_next: list[str]


SYSTEM = (
    "You assist a generic API bulk-calling tool. Users map spreadsheet columns to the fields of a JSON "
    "request template, validate rows and send API calls. Answer only with the requested structure; "
    "be precise and conservative - when unsure, say so via low confidence or an empty value."
)


class AiAssistant:
    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model = model or os.environ.get("APIRUNNER_AI_MODEL", DEFAULT_MODEL)
        self._client = None

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _get_client(self):
        if not self.enabled:
            raise AiError("AI is disabled: set an Anthropic API key in Settings or ANTHROPIC_API_KEY.")
        if self._client is None:
            import anthropic

            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
        return self._client

    async def _ask(self, prompt: str, schema: type[BaseModel]) -> Any:
        import anthropic

        client = self._get_client()
        try:
            response = await client.messages.parse(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                output_format=schema,
                output_config={"effort": "low"},
            )
        except anthropic.AuthenticationError as exc:
            raise AiError("Invalid Anthropic API key.") from exc
        except anthropic.RateLimitError as exc:
            raise AiError("AI rate limit reached, try again shortly.") from exc
        except anthropic.APIStatusError as exc:
            raise AiError(f"AI request failed ({exc.status_code}).") from exc
        except anthropic.APIConnectionError as exc:
            raise AiError("Could not reach the AI service.") from exc
        if response.stop_reason == "refusal" or response.parsed_output is None:
            raise AiError("The AI declined or returned no usable answer.")
        return response.parsed_output

    async def suggest_mapping(self, columns: list[str], fields: list[str], samples: list[dict]) -> MappingSuggestion:
        prompt = (
            "Map each template field to the best spreadsheet column (use each column at most once; "
            "column \"\" if nothing fits). Confidence is 0..1.\n"
            f"Fields: {json.dumps(fields)}\nColumns: {json.dumps(columns)}\n"
            f"Sample rows: {json.dumps(samples[:MAX_SAMPLES], default=str, ensure_ascii=False)}"
        )
        return await self._ask(prompt, MappingSuggestion)

    async def template_from_sample(self, sample: str) -> TemplateDraft:
        prompt = (
            "Build a request template from this sample (a curl command, an OpenAPI snippet or a JSON payload). "
            "Replace concrete values that would vary per record with placeholders: {{name}} for strings or "
            "{{name:type}} where type is number, integer, boolean, date, array or object. Use dotted names for "
            "nested fields (e.g. {{address.city}}). Keep auth headers as-is. body must be valid JSON text or \"\".\n\n"
            f"Sample:\n{sample}"
        )
        return await self._ask(prompt, TemplateDraft)

    async def request_from_prompt(self, description: str, current: dict | None = None) -> RequestDraft:
        prompt = (
            "Build an HTTP request from the user's description. Put values the user will vary into the URL or "
            "body as {{name}} placeholders and list each one in params with location \"auto\" and its value; "
            "use location \"query\" or \"header\" for plain query/header parameters. body must be valid JSON "
            "text or \"\" (always \"\" for GET). Do not invent secrets - leave auth to the user.\n"
            f"Current request (may be empty): {json.dumps(current or {}, ensure_ascii=False)}\n\n"
            f"Description:\n{description}"
        )
        return await self._ask(prompt, RequestDraft)

    async def analyze_response(self, request: dict, status: int | None, headers: dict, body: str,
                               error: str = "") -> ResponseAnalysis:
        prompt = (
            "Analyse this API response for the user: classify the outcome, summarise it in one or two sentences, "
            "list key points, extract the most useful values and suggest next steps (for errors: the likely "
            "cause and how to fix the request).\n"
            f"Request: {json.dumps(request, default=str, ensure_ascii=False)[:4000]}\n"
            f"Status: {status}\nTransport error: {error or 'none'}\n"
            f"Headers: {json.dumps(headers, ensure_ascii=False)[:2000]}\n"
            f"Body (truncated):\n{body[:12000]}"
        )
        return await self._ask(prompt, ResponseAnalysis)

    async def suggest_fixes(self, invalid: list[dict]) -> FixSuggestions:
        prompt = (
            "These spreadsheet cells failed validation. Suggest a corrected value only when the intended value "
            "is clear (e.g. date format, number with a currency sign, yes/no to boolean). Skip the rest.\n"
            f"{json.dumps(invalid[:50], default=str, ensure_ascii=False)}"
        )
        return await self._ask(prompt, FixSuggestions)

    async def explain_failures(self, failures: list[dict]) -> FailureInsights:
        prompt = (
            "Group these failed API calls by root cause and suggest how to fix each group.\n"
            f"{json.dumps(failures[:50], default=str, ensure_ascii=False)}"
        )
        return await self._ask(prompt, FailureInsights)
