"""JSON template page: define the generic request contract and its fields."""

from __future__ import annotations

import json

from nicegui import ui

from apirunner.core.models import FieldSpec, RequestTemplate
from apirunner.core.template import extract_fields, sample_json_to_template
from apirunner.infra.ai import AiError
from apirunner.infra.excel_io import write_template
from apirunner.services import services
from apirunner.ui.theme import frame
from apirunner.ui.widgets import AuthEditor, json_editor, parse_headers

TYPES = ["string", "number", "integer", "boolean", "date", "array", "object"]
EXAMPLE_BODY = json.dumps({
    "name": "{{name}}",
    "email": "{{email}}",
    "age": "{{age:integer}}",
    "address": {"city": "{{address.city}}"},
}, indent=2)


def page() -> None:
    tpl = RequestTemplate(name="Create user", method="POST", url="https://httpbin.org/anything/users",
                          headers={"Accept": "application/json"}, body=EXAMPLE_BODY)
    tpl.fields = extract_fields(tpl)

    with frame("/templates", "JSON Templates",
               "Describe the request once with {{placeholders}}; Excel columns map to these fields."):
        with ui.row().classes("w-full items-start no-wrap gap-4"):
            with ui.card().classes("soft-card w-64"):
                ui.label("Saved templates").classes("font-bold")
                saved_list = ui.column().classes("w-full gap-1")
                ui.separator()
                ui.button("New", icon="add", on_click=lambda: load(RequestTemplate())).props("flat")
                ui.button("Export all", icon="file_download", on_click=lambda: ui.download.content(
                    services.storage.export_templates(), "templates.json")).props("flat")
                ui.upload(label="Import JSON", auto_upload=True, on_upload=lambda e: import_templates(e)
                          ).props("accept=.json flat dense").classes("w-full")

            with ui.column().classes("flex-grow gap-4"):
                with ui.card().classes("soft-card w-full"):
                    with ui.row().classes("w-full no-wrap"):
                        name = ui.input("Template name", value=tpl.name).classes("w-64")
                        method = ui.select(["GET", "POST", "PUT", "PATCH", "DELETE"], value=tpl.method,
                                           label="Method").classes("w-28")
                        url = ui.input("URL (placeholders allowed)", value=tpl.url).classes("flex-grow")
                    ui.label("JSON body format").classes("font-medium")
                    body = json_editor(tpl.body, height="260px")
                    with ui.expansion("Headers", icon="list").classes("w-full"):
                        headers = json_editor(json.dumps(tpl.headers, indent=2), height="120px")
                    with ui.expansion("Authentication", icon="lock").classes("w-full"):
                        auth_editor = AuthEditor(tpl.auth)
                    with ui.row():
                        ui.button("Detect fields", icon="auto_fix_high", on_click=lambda: detect()).props("outline")
                        ui.button("Sample JSON → template", icon="transform",
                                  on_click=lambda: convert_sample()).props("outline color=accent")
                        ai_btn = ui.button("AI: template from curl / sample", icon="auto_awesome",
                                           on_click=lambda: ai_dialog.open()).props("outline color=secondary")
                        ai_btn.set_visibility(services.ai().enabled)

                with ui.card().classes("soft-card w-full"):
                    with ui.row().classes("w-full items-center"):
                        ui.label("Fields (Excel columns)").classes("font-bold text-lg")
                        ui.space()
                        ui.button("Download Excel template", icon="grid_on", on_click=lambda: download_template()
                                  ).props("unelevated color=positive")
                    grid = ui.aggrid({
                        "columnDefs": [
                            {"field": "name", "headerName": "Field / column name", "editable": True, "flex": 2},
                            {"field": "type", "editable": True, "cellEditor": "agSelectCellEditor",
                             "cellEditorParams": {"values": TYPES}, "flex": 1},
                            {"field": "required", "editable": True, "cellDataType": "boolean", "flex": 1},
                            {"field": "regex", "headerName": "Regex", "editable": True, "flex": 1},
                            {"field": "allowed", "headerName": "Allowed (comma separated)", "editable": True, "flex": 2},
                            {"field": "default", "headerName": "Default", "editable": True, "flex": 1},
                        ],
                        "rowData": [],
                        "stopEditingWhenCellsLoseFocus": True,
                    }).classes("w-full h-64")
                    with ui.row():
                        ui.button("Save template", icon="save", on_click=lambda: save()).props("unelevated")
                        ui.button("Delete", icon="delete", on_click=lambda: delete()).props("flat color=negative")

    with ui.dialog() as ai_dialog, ui.card().classes("w-[640px]"):
        ui.label("Generate a template with AI").classes("text-lg font-bold")
        ui.label("Paste a curl command, an OpenAPI snippet or a sample JSON payload.").classes("text-gray-500")
        ai_input = ui.textarea().classes("w-full").props("outlined autogrow")
        with ui.row():
            gen_btn = ui.button("Generate", icon="auto_awesome", on_click=lambda: ai_generate())
            ui.button("Cancel", on_click=ai_dialog.close).props("flat")

    def rows_from_fields(fields: list[FieldSpec]) -> list[dict]:
        return [{"name": f.name, "type": f.type, "required": f.required, "regex": f.regex or "",
                 "allowed": ", ".join(f.allowed or []), "default": "" if f.default is None else str(f.default)}
                for f in fields]

    async def fields_from_grid() -> list[FieldSpec]:
        rows = await grid.get_client_data()
        return [FieldSpec(name=r["name"].strip(), type=r.get("type") or "string", required=bool(r.get("required")),
                          regex=(r.get("regex") or None),
                          allowed=[a.strip() for a in str(r.get("allowed") or "").split(",") if a.strip()] or None,
                          default=(r.get("default") or None))
                for r in rows if str(r.get("name") or "").strip()]

    def set_fields(fields: list[FieldSpec]) -> None:
        grid.options["rowData"] = rows_from_fields(fields)
        grid.update()

    def current() -> RequestTemplate:
        return RequestTemplate(name=name.value.strip() or "Untitled", method=method.value, url=url.value,
                               headers=parse_headers(headers.value), body=body.value,
                               auth=auth_editor.auth.model_copy())

    async def detect() -> None:
        try:
            t = current()
        except ValueError as exc:
            ui.notify(f"Headers are not valid JSON: {exc}", type="negative")
            return
        t.fields = await fields_from_grid()
        t.fields = extract_fields(t)
        set_fields(t.fields)
        ui.notify(f"{len(t.fields)} field(s) detected", type="positive")

    async def convert_sample() -> None:
        try:
            sample = json.loads(body.value)
        except ValueError:
            ui.notify("Body is not valid JSON", type="negative")
            return
        body.value = json.dumps(sample_json_to_template(sample), indent=2)
        await detect()

    async def save() -> None:
        try:
            t = current()
        except ValueError as exc:
            ui.notify(f"Headers are not valid JSON: {exc}", type="negative")
            return
        t.fields = await fields_from_grid()
        if not t.fields:
            t.fields = extract_fields(t)
            set_fields(t.fields)
        services.storage.save_template(t)
        ui.notify(f"Saved '{t.name}'", type="positive")
        render_saved()

    def delete() -> None:
        services.storage.delete_template(name.value)
        ui.notify(f"Deleted '{name.value}'")
        render_saved()

    async def download_template() -> None:
        fields = await fields_from_grid()
        if not fields:
            ui.notify("No fields yet - click Detect fields", type="warning")
            return
        ui.download.content(write_template(fields), f"{name.value or 'template'}.xlsx")

    def load(t: RequestTemplate) -> None:
        name.value, method.value, url.value, body.value = t.name, t.method, t.url, t.body
        headers.value = json.dumps(t.headers, indent=2)
        auth_editor.set(t.auth)
        set_fields(t.fields or extract_fields(t))

    async def import_templates(e) -> None:
        try:
            count = services.storage.import_templates((await e.file.read()).decode("utf-8"))
            ui.notify(f"Imported {count} template(s)", type="positive")
            render_saved()
        except Exception as exc:
            ui.notify(f"Import failed: {exc}", type="negative")

    async def ai_generate() -> None:
        gen_btn.props("loading")
        try:
            draft = await services.ai().template_from_sample(ai_input.value)
        except AiError as exc:
            ui.notify(str(exc), type="negative")
            return
        finally:
            gen_btn.props(remove="loading")
        method.value = draft.method.upper() if draft.method.upper() in method.options else "POST"
        url.value = draft.url
        headers.value = json.dumps({h.name: h.value for h in draft.headers}, indent=2)
        body.value = draft.body
        ai_dialog.close()
        await detect()
        if draft.notes:
            ui.notify(draft.notes, multi_line=True, timeout=8000)

    def render_saved() -> None:
        saved_list.clear()
        with saved_list:
            items = services.storage.list_templates()
            if not items:
                ui.label("None yet").classes("text-gray-400 italic")
            for t in items:
                ui.button(t.name, icon="description", on_click=lambda t=t: load(t)).props(
                    "flat align=left no-caps").classes("w-full")

    set_fields(tpl.fields)
    render_saved()
