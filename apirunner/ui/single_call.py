"""Single call page: method + URL + params (auto-detected from placeholders) + JSON body."""

from __future__ import annotations

import json

from nicegui import ui

from apirunner.core.binding import bind_single, detect_param_names, sync_params, to_curl
from apirunner.core.executor import call_with_retry
from apirunner.core.models import AuthConfig, Param, ParamLocation, RequestTemplate, RunOptions
from apirunner.infra.ai import AiError
from apirunner.services import services
from apirunner.ui.theme import frame, status_badge
from apirunner.ui.widgets import AuthEditor, json_editor, parse_headers, pretty

METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]
LOCATIONS = {ParamLocation.AUTO.value: "placeholder", ParamLocation.QUERY.value: "query", ParamLocation.HEADER.value: "header"}


def page() -> None:
    state = {
        "method": "GET",
        "url": "https://jsonplaceholder.typicode.com/posts/{{id}}",
        "headers": '{\n  "Accept": "application/json"\n}',
        "body": "",
        "params": [Param(name="id", value="1")],
        "auth": AuthConfig(),
    }

    def template() -> RequestTemplate:
        return RequestTemplate(method=state["method"], url=state["url"], headers=parse_headers(state["headers"]),
                               body=state["body"], auth=state["auth"])

    with frame("/", "Single Call",
               "Type a URL with {{placeholders}} or :params - parameter fields appear automatically."):
        templates = services.storage.list_templates()
        with ui.card().classes("soft-card w-full"):
            with ui.row().classes("w-full items-center no-wrap"):
                method = ui.select(METHODS, value=state["method"],
                                   on_change=lambda e: (state.update(method=e.value), refresh())).classes("w-28")
                url = ui.input("Request URL", value=state["url"],
                               on_change=lambda e: (state.update(url=e.value), refresh())).classes("flex-grow")
                url.props("outlined clearable")
                send_btn = ui.button("Send", icon="send", on_click=lambda: send()).props("unelevated size=lg")
            with ui.row().classes("items-center"):
                if templates:
                    ui.select({t.name: t.name for t in templates}, label="Load from saved template",
                              on_change=lambda e: load_template(e.value)).classes("w-72")
                ai_req_btn = ui.button("AI: describe the request", icon="auto_awesome",
                                       on_click=lambda: ai_dialog.open()).props("outline color=secondary")
                ai_req_btn.set_visibility(services.ai().enabled)

        with ui.tabs().classes("w-full") as tabs:
            t_params = ui.tab("Parameters", icon="tune")
            t_body = ui.tab("Body (JSON)", icon="data_object")
            t_headers = ui.tab("Headers", icon="list")
            t_auth = ui.tab("Auth", icon="lock")
            t_preview = ui.tab("Preview", icon="visibility")
        with ui.tab_panels(tabs, value=t_params).classes("w-full soft-card"):
            with ui.tab_panel(t_params):
                ui.label("Placeholders found in the URL, body and headers are listed here automatically. "
                         "Add extra query or header parameters with the button.").classes("text-gray-500 text-sm")
                params_box = ui.column().classes("w-full gap-1")
                ui.button("Add parameter", icon="add", on_click=lambda: add_param()).props("flat")
            with ui.tab_panel(t_body):
                body = json_editor(state["body"], on_change=lambda e: (state.update(body=e.value), refresh()))
                ui.label('Tip: use "{{age:number}}" to send a typed value instead of a string.').classes(
                    "text-gray-500 text-sm")
            with ui.tab_panel(t_headers):
                headers = json_editor(state["headers"], height="160px",
                                      on_change=lambda e: (state.update(headers=e.value), refresh()))
            with ui.tab_panel(t_auth):
                auth_editor = AuthEditor(state["auth"])
            with ui.tab_panel(t_preview):
                preview = ui.code("", language="bash").classes("w-full")

        result_card = ui.card().classes("soft-card w-full")
        result_card.set_visibility(False)

    with ui.dialog() as ai_dialog, ui.card().classes("w-[640px]"):
        ui.label("Describe the API call").classes("text-lg font-bold")
        ui.label('e.g. "Create a user on https://api.example.com/users with name Alice, email alice@x.com '
                 'and age 31"').classes("text-gray-500 text-sm")
        ai_text = ui.textarea().classes("w-full").props("outlined autogrow")
        with ui.row():
            ai_go = ui.button("Build request", icon="auto_awesome", on_click=lambda: ai_build())
            ui.button("Cancel", on_click=ai_dialog.close).props("flat")

    def render_params() -> None:
        params_box.clear()
        with params_box:
            if not state["params"]:
                ui.label("No parameters - add {{name}} to the URL or body.").classes("text-gray-400 italic")
            for p in state["params"]:
                with ui.row().classes("w-full items-center no-wrap"):
                    auto = p.location == ParamLocation.AUTO
                    name_in = ui.input("Name", value=p.name).classes("w-56").props("dense outlined")
                    name_in.on_value_change(lambda e, p=p: (setattr(p, "name", e.value), update_preview()))
                    if auto:
                        name_in.props("readonly")
                    ui.input("Value", value=p.value,
                             on_change=lambda e, p=p: (setattr(p, "value", e.value), update_preview())
                             ).classes("flex-grow").props("dense outlined")
                    ui.select(LOCATIONS, value=p.location.value,
                              on_change=lambda e, p=p: (setattr(p, "location", ParamLocation(e.value)), refresh())
                              ).classes("w-36").props("dense outlined")
                    if not auto:
                        ui.button(icon="delete", on_click=lambda p=p: remove_param(p)).props("flat round color=negative")

    def refresh() -> None:
        names = detect_param_names(state["url"], state["body"], _safe_headers())
        new = sync_params(state["params"], names)
        if [(p.name, p.location) for p in new] != [(p.name, p.location) for p in state["params"]]:
            state["params"] = new
            render_params()
        update_preview()

    def _safe_headers() -> dict[str, str]:
        try:
            return parse_headers(state["headers"])
        except ValueError:
            return {}

    def update_preview() -> None:
        try:
            preview.content = to_curl(bind_single(template(), state["params"]))
        except Exception as exc:  # invalid headers JSON while typing
            preview.content = f"# cannot build request yet: {exc}"

    def add_param() -> None:
        state["params"].append(Param(name="", location=ParamLocation.QUERY))
        render_params()

    def remove_param(p: Param) -> None:
        state["params"].remove(p)
        render_params()
        update_preview()

    def load_template(name: str) -> None:
        t = services.storage.get_template(name)
        if not t:
            return
        state.update(method=t.method, url=t.url, body=t.body, headers=json.dumps(t.headers, indent=2))
        method.value, url.value, body.value, headers.value = t.method, t.url, t.body, state["headers"]
        auth_editor.set(t.auth)
        refresh()

    async def ai_build() -> None:
        ai_go.props("loading")
        try:
            draft = await services.ai().request_from_prompt(
                ai_text.value, {"method": state["method"], "url": state["url"], "body": state["body"]})
        except AiError as exc:
            ui.notify(str(exc), type="negative")
            return
        finally:
            ai_go.props(remove="loading")
        m = draft.method.upper()
        state.update(method=m if m in METHODS else "GET", url=draft.url, body=draft.body,
                     headers=json.dumps({h.name: h.value for h in draft.headers}, indent=2))
        state["params"] = [Param(name=p.name, value=p.value,
                                 location=ParamLocation(p.location) if p.location in LOCATIONS else ParamLocation.AUTO)
                           for p in draft.params]
        method.value, url.value, body.value, headers.value = state["method"], state["url"], state["body"], state[
            "headers"]
        render_params()
        refresh()
        ai_dialog.close()
        if draft.notes:
            ui.notify(draft.notes, multi_line=True, timeout=8000)

    async def ai_analyze(result, request, panel, btn) -> None:
        btn.props("loading")
        try:
            a = await services.ai().analyze_response(request.model_dump(), result.http_code,
                                                     result.response_headers, result.response_text, result.error)
        except AiError as exc:
            ui.notify(str(exc), type="negative")
            return
        finally:
            btn.props(remove="loading")
        panel.clear()
        color = {"success": "border-green-500"}.get(a.outcome, "border-pink-500")
        with panel, ui.card().classes(f"w-full border-l-4 {color}"):
            with ui.row().classes("items-center"):
                ui.icon("auto_awesome", color="secondary")
                ui.badge(a.outcome, color="positive" if a.outcome == "success" else "negative")
                ui.label(a.summary).classes("font-medium")
            for point in a.key_points:
                ui.label(f"• {point}")
            if a.extracted:
                with ui.row():
                    for kv in a.extracted:
                        ui.chip(f"{kv.key}: {kv.value}", color="accent").props("outline dense")
            if a.suggested_next:
                ui.label("Next steps").classes("font-bold mt-2")
                for step in a.suggested_next:
                    ui.label(f"→ {step}").classes("text-gray-600")

    async def send() -> None:
        try:
            request = bind_single(template(), state["params"])
        except Exception as exc:
            ui.notify(f"Invalid request: {exc}", type="negative")
            return
        send_btn.props("loading")
        sender = services.sender(state["auth"])
        try:
            result = await call_with_retry(sender, request, RunOptions(retry={"max_attempts": 1}))
        finally:
            await sender.aclose()
            send_btn.props(remove="loading")
        show_result(result, request)

    def show_result(result, request) -> None:
        result_card.clear()
        result_card.set_visibility(True)
        with result_card:
            with ui.row().classes("items-center gap-4"):
                ui.label("Response").classes("text-lg font-bold")
                status_badge(result.http_code)
                ui.chip(f"{result.elapsed_ms:.0f} ms", icon="timer", color="accent").props("outline")
                ui.chip(f"{len(result.response_text.encode())} bytes", icon="straighten", color="primary").props(
                    "outline")
                if result.error and result.http_code is None:
                    ui.label(result.error).classes("text-negative")
                ui.space()
                analyze_btn = ui.button("AI analyze response", icon="auto_awesome").props("outline color=secondary")
                analyze_btn.set_visibility(services.ai().enabled)
            analysis = ui.column().classes("w-full")
            analyze_btn.on_click(lambda: ai_analyze(result, request, analysis, analyze_btn))
            with ui.tabs() as rtabs:
                rb = ui.tab("Body")
                rh = ui.tab("Headers")
            with ui.tab_panels(rtabs, value=rb).classes("w-full"):
                with ui.tab_panel(rb):
                    json_editor(pretty(result.response_text), height="360px")
                with ui.tab_panel(rh):
                    json_editor(json.dumps(result.response_headers, indent=2), height="300px")

    render_params()
    update_preview()
