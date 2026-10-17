"""Bind parameter values into a request template, producing a ready-to-send request."""

from __future__ import annotations

from typing import Any

from .models import Param, ParamLocation, PreparedRequest, RequestTemplate
from .template import extract_placeholders, render_body, render_text, render_url


def detect_param_names(url: str, body: str = "", headers: dict[str, str] | None = None) -> list[str]:
    """Names of every placeholder the user must fill, in order (URL first)."""
    names: list[str] = []
    sources = [(url, True), (body, False)] + [(v, False) for v in (headers or {}).values()]
    for text, is_url in sources:
        for name, _ in extract_placeholders(text, include_path_params=is_url):
            if name not in names:
                names.append(name)
    return names


def sync_params(current: list[Param], names: list[str]) -> list[Param]:
    """Keep typed values for placeholders that still exist, add new ones, keep manual params."""
    by_name = {p.name: p for p in current}
    synced = [by_name.get(n) or Param(name=n) for n in names]
    synced += [p for p in current if p.location != ParamLocation.AUTO and p.name not in names]
    return synced


def build_request(
    template: RequestTemplate, values: dict[str, Any], extra: list[Param] | None = None
) -> PreparedRequest:
    url = render_url(template.url, values)
    headers = {k: render_text(v, values) for k, v in template.headers.items()}
    json_body, text_body = render_body(template.body, values)
    params: dict[str, str] = {}
    for p in extra or []:
        if p.location == ParamLocation.QUERY and p.name:
            params[p.name] = p.value
        elif p.location == ParamLocation.HEADER and p.name:
            headers[p.name] = p.value
    if template.method == "GET":
        json_body, text_body = None, None
    return PreparedRequest(
        method=template.method, url=url, headers=headers, params=params, json_body=json_body, text_body=text_body
    )


def bind_single(template: RequestTemplate, params: list[Param]) -> PreparedRequest:
    """Single-call helper: placeholder params become values, others go to query/header."""
    values = {p.name: p.value for p in params if p.location == ParamLocation.AUTO}
    return build_request(template, values, params)


def to_curl(req: PreparedRequest) -> str:
    import json
    from urllib.parse import urlencode

    url = req.url + (("&" if "?" in req.url else "?") + urlencode(req.params) if req.params else "")
    parts = [f"curl -X {req.method} '{url}'"]
    parts += [f"-H '{k}: {v}'" for k, v in req.headers.items()]
    if req.json_body is not None:
        parts.append(f"-H 'Content-Type: application/json' -d '{json.dumps(req.json_body, ensure_ascii=False)}'")
    elif req.text_body:
        parts.append(f"-d '{req.text_body}'")
    return " \\\n  ".join(parts)
