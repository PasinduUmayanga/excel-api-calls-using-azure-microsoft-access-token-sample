"""Reusable form widgets."""

from __future__ import annotations

import json

from nicegui import ui

from apirunner.core.models import AuthConfig, AuthType

AUTH_LABELS = {
    AuthType.NONE.value: "No auth",
    AuthType.BEARER.value: "Bearer token",
    AuthType.API_KEY.value: "API key",
    AuthType.BASIC.value: "Basic",
    AuthType.AZURE_AD.value: "Azure AD (client credentials)",
}


class AuthEditor:
    """Edits an AuthConfig in place; shows only the inputs relevant to the chosen type."""

    def __init__(self, auth: AuthConfig) -> None:
        self.auth = auth
        with ui.column().classes("w-full gap-2"):
            ui.select(AUTH_LABELS, label="Authentication", value=auth.type.value,
                      on_change=lambda e: self._set_type(e.value)).classes("w-72")
            self.container = ui.column().classes("w-full gap-2")
        self._render()

    def _set_type(self, value: str) -> None:
        self.auth.type = AuthType(value)
        self._render()

    def set(self, auth: AuthConfig) -> None:
        self.auth.__dict__.update(auth.model_dump())
        self._render()

    def _input(self, label: str, attr: str, password: bool = False) -> None:
        ui.input(label, value=getattr(self.auth, attr), password=password, password_toggle_button=password,
                 on_change=lambda e: setattr(self.auth, attr, e.value)).classes("w-full")

    def _render(self) -> None:
        self.container.clear()
        t = self.auth.type
        with self.container:
            if t == AuthType.BEARER:
                self._input("Token", "token", password=True)
            elif t == AuthType.API_KEY:
                with ui.row().classes("w-full no-wrap"):
                    self._input("Key name", "key_name")
                    self._input("Key value", "key_value", password=True)
                    ui.select(["header", "query"], label="Send in", value=self.auth.key_in,
                              on_change=lambda e: setattr(self.auth, "key_in", e.value)).classes("w-32")
            elif t == AuthType.BASIC:
                with ui.row().classes("w-full no-wrap"):
                    self._input("Username", "username")
                    self._input("Password", "password", password=True)
            elif t == AuthType.AZURE_AD:
                with ui.grid(columns=2).classes("w-full"):
                    self._input("Tenant ID", "tenant_id")
                    self._input("Client ID", "client_id")
                    self._input("Client secret", "client_secret", password=True)
                    self._input("Scope (e.g. https://graph.microsoft.com/.default)", "scope")


def json_editor(value: str, height: str = "220px", on_change=None, readonly: bool = False) -> ui.codemirror:
    editor = ui.codemirror(value, language="JSON", line_wrapping=True, on_change=on_change)
    editor.classes("w-full border rounded-lg").style(f"height: {height}")
    if readonly:
        editor.props("disable")
    return editor


def parse_headers(text: str) -> dict[str, str]:
    """Headers editor accepts a JSON object or `Key: Value` lines."""
    text = (text or "").strip()
    if not text:
        return {}
    if text.startswith("{"):
        return {str(k): str(v) for k, v in json.loads(text).items()}
    headers = {}
    for line in text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip()] = v.strip()
    return headers


def pretty(text: str) -> str:
    try:
        return json.dumps(json.loads(text), indent=2, ensure_ascii=False)
    except (ValueError, TypeError):
        return text
