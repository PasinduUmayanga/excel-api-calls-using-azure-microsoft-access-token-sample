"""Placeholder parsing, type coercion and rendering of request templates.

Placeholder syntax:
    {{name}}            string field
    {{age:number}}      typed field (string, number, integer, boolean, date, array, object)
    :id                 path parameter inside a URL (treated like {{id}})
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any
from urllib.parse import quote

from .models import FieldSpec, FieldType, RequestTemplate

PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][\w.\-\[\]]*)\s*(?::\s*(\w+))?\s*\}\}")
PATH_PARAM_RE = re.compile(r"(?<=/):([A-Za-z_]\w*)")
_VALID_TYPES = {"string", "number", "integer", "boolean", "date", "array", "object"}


class CoercionError(ValueError):
    pass


def extract_placeholders(text: str, include_path_params: bool = False) -> list[tuple[str, FieldType]]:
    """Return unique (name, type) placeholders in order of appearance."""
    found: dict[str, FieldType] = {}
    for m in PLACEHOLDER_RE.finditer(text or ""):
        name, typ = m.group(1), (m.group(2) or "string").lower()
        found.setdefault(name, typ if typ in _VALID_TYPES else "string")  # type: ignore[arg-type]
    if include_path_params:
        path = (text or "").split("?", 1)[0].split("://", 1)[-1]
        for m in PATH_PARAM_RE.finditer(path):
            found.setdefault(m.group(1), "string")
    return list(found.items())


def extract_fields(template: RequestTemplate) -> list[FieldSpec]:
    """Derive the field list from URL, headers and body; keeps existing field settings."""
    existing = {f.name: f for f in template.fields}
    seen: dict[str, FieldSpec] = {}
    sources = [(template.url, True), (template.body, False)] + [(v, False) for v in template.headers.values()]
    for text, is_url in sources:
        for name, typ in extract_placeholders(text, include_path_params=is_url):
            if name not in seen:
                seen[name] = existing.get(name) or FieldSpec(name=name, type=typ)
    return list(seen.values())


def sample_json_to_template(sample: Any, prefix: str = "") -> Any:
    """Turn plain sample JSON into a placeholder template, e.g. {"a": 1} -> {"a": "{{a:number}}"}."""
    if isinstance(sample, dict):
        return {k: sample_json_to_template(v, f"{prefix}{k}" if not prefix else f"{prefix}.{k}") for k, v in sample.items()}
    if isinstance(sample, list):
        return f"{{{{{prefix}:array}}}}"
    typ = _infer_type(sample)
    return f"{{{{{prefix}}}}}" if typ == "string" else f"{{{{{prefix}:{typ}}}}}"


def _infer_type(value: Any) -> FieldType:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, (dict,)):
        return "object"
    return "string"


def is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def coerce(value: Any, typ: FieldType) -> Any:
    """Convert a raw cell/text value to the field type. Raises CoercionError."""
    if is_blank(value):
        return None
    try:
        if typ == "string":
            if isinstance(value, float) and value.is_integer():
                return str(int(value))
            return value.isoformat() if isinstance(value, (date, datetime)) else str(value)
        if typ == "integer":
            if isinstance(value, bool):
                raise ValueError
            f = float(str(value).strip())
            if not f.is_integer():
                raise ValueError
            return int(f)
        if typ == "number":
            if isinstance(value, bool):
                raise ValueError
            f = float(str(value).strip())
            return int(f) if f.is_integer() else f
        if typ == "boolean":
            if isinstance(value, bool):
                return value
            s = str(value).strip().lower()
            if s in {"true", "1", "yes", "y"}:
                return True
            if s in {"false", "0", "no", "n"}:
                return False
            raise ValueError
        if typ == "date":
            if isinstance(value, datetime):
                return value.date().isoformat()
            if isinstance(value, date):
                return value.isoformat()
            return date.fromisoformat(str(value).strip()[:10]).isoformat()
        if typ == "array":
            if isinstance(value, list):
                return value
            s = str(value).strip()
            if s.startswith("["):
                return json.loads(s)
            return [p.strip() for p in s.split(",") if p.strip()]
        if typ == "object":
            if isinstance(value, dict):
                return value
            parsed = json.loads(str(value))
            if not isinstance(parsed, dict):
                raise ValueError
            return parsed
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise CoercionError(f"expected {typ}, got {value!r}") from exc
    return value


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def render_text(text: str, values: dict[str, Any], url_encode: bool = False) -> str:
    def sub(m: re.Match[str]) -> str:
        v = _text(values.get(m.group(1)))
        return quote(v, safe="") if url_encode else v

    return PLACEHOLDER_RE.sub(sub, text or "")


def render_url(url: str, values: dict[str, Any]) -> str:
    rendered = render_text(url, values, url_encode=True)
    head, sep, query = rendered.partition("?")
    scheme, sep2, rest = head.partition("://")
    if not sep2:
        scheme, rest = "", head

    def sub(m: re.Match[str]) -> str:
        name = m.group(1)
        return quote(_text(values[name]), safe="") if name in values else m.group(0)

    rest = PATH_PARAM_RE.sub(sub, rest)
    return (f"{scheme}://{rest}" if sep2 else rest) + (sep + query if sep else "")


def render_body(body: str, values: dict[str, Any]) -> tuple[Any, str | None]:
    """Render a body. Returns (json_value, None) for JSON bodies or (None, text) otherwise.

    A string that is exactly one placeholder keeps the value's type, so
    {"age": "{{age:number}}"} renders as {"age": 42}, not {"age": "42"}.
    """
    if not (body or "").strip():
        return None, None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return None, render_text(body, values)

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            return {k: walk(v) for k, v in node.items()}
        if isinstance(node, list):
            return [walk(v) for v in node]
        if isinstance(node, str):
            full = PLACEHOLDER_RE.fullmatch(node.strip())
            if full:
                return values.get(full.group(1))
            return render_text(node, values)
        return node

    return walk(parsed), None
