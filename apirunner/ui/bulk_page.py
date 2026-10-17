"""Excel bulk page: upload -> map columns -> validate -> run -> download Success/Failed -> retry."""

from __future__ import annotations

import json

from nicegui import ui

from apirunner.core.executor import create_job, run_rows
from apirunner.core.mapping import auto_map, usable_columns
from apirunner.core.models import CallStatus, Job, RequestTemplate, RetryPolicy, RunOptions
from apirunner.core.validation import RowValidation, validate_headers, validate_rows
from apirunner.infra.ai import AiError
from apirunner.infra.excel_io import Table, read_table, write_invalid_rows, write_results, write_template
from apirunner.services import services
from apirunner.ui.theme import frame, stat_card

NONE = "— not mapped —"


class BulkState:
    def __init__(self) -> None:
        self.template: RequestTemplate | None = None
        self.file_bytes: bytes = b""
        self.file_name: str = ""
        self.table: Table = Table()
        self.mapping: dict[str, str | None] = {}
        self.validations: list[RowValidation] = []
        self.job: Job | None = None
        self.running = False

    @property
    def valid_count(self) -> int:
        return sum(v.valid for v in self.validations)

    @property
    def invalid_count(self) -> int:
        return len(self.validations) - self.valid_count


def page() -> None:
    s = BulkState()
    templates = {t.name: t for t in services.storage.list_templates()}

    with frame("/bulk", "Excel Bulk",
               "Upload an Excel/CSV file, map columns to your JSON template, validate, send, and retry failures."):
        if not templates:
            with ui.card().classes("soft-card w-full items-center p-8"):
                ui.icon("data_object", size="48px", color="primary")
                ui.label("Create a JSON template first").classes("text-lg font-bold")
                ui.button("Go to JSON Templates", icon="arrow_forward",
                          on_click=lambda: ui.navigate.to("/templates"))
            return

        with ui.stepper().props("vertical animated header-nav=false").classes("w-full soft-card") as stepper:
            # Step 1 - template + upload
            with ui.step("Choose template & upload file", icon="upload_file"):
                with ui.row().classes("items-end"):
                    tpl_select = ui.select(list(templates), label="JSON template",
                                           on_change=lambda e: choose_template(e.value)).classes("w-72").mark("template-select")
                    ui.button("Download Excel template", icon="grid_on",
                              on_click=lambda: s.template and ui.download.content(
                                  write_template(s.template.fields), f"{s.template.name}.xlsx")
                              ).props("outline color=positive")
                fields_info = ui.row().classes("gap-1")
                ui.upload(label="Drop .xlsx or .csv here (Failed.xlsx can be re-uploaded as-is)",
                          auto_upload=True, on_upload=lambda e: on_upload(e)).props(
                    'accept=".xlsx,.xlsm,.csv" color=primary').classes("w-full")
                with ui.row().classes("items-center"):
                    file_label = ui.label("").classes("text-gray-600")
                    sheet_select = ui.select([], label="Sheet", on_change=lambda e: load_sheet(e.value)
                                             ).classes("w-48")
                    sheet_select.set_visibility(False)
                preview = ui.aggrid({"columnDefs": [], "rowData": []}).classes("w-full h-56")
                preview.set_visibility(False)
                with ui.stepper_navigation():
                    next1 = ui.button("Next: map columns", icon="arrow_forward", on_click=lambda: go_mapping())
                    next1.disable()

            # Step 2 - mapping
            with ui.step("Map columns to JSON fields", icon="swap_horiz"):
                ui.label("Columns are matched automatically (exact, case/space-insensitive, then fuzzy). "
                         "Adjust any field below.").classes("text-gray-500 text-sm")
                with ui.row():
                    ui.button("Auto map", icon="auto_fix_high", on_click=lambda: (do_auto_map(), render_mapping())
                              ).props("outline")
                    ai_map_btn = ui.button("AI suggest mapping", icon="auto_awesome", on_click=lambda: ai_map()
                                           ).props("outline color=secondary")
                mapping_box = ui.column().classes("w-full gap-1")
                header_report = ui.column().classes("w-full")
                with ui.stepper_navigation():
                    ui.button("Back", on_click=stepper.previous).props("flat")
                    ui.button("Next: validate", icon="fact_check", on_click=lambda: go_validate())

            # Step 3 - validation
            with ui.step("Validate rows", icon="fact_check"):
                with ui.row().classes("gap-4"):
                    total_lbl = stat_card("Rows", "total", "table_rows")
                    valid_lbl = stat_card("Valid", "success", "check_circle")
                    invalid_lbl = stat_card("Invalid", "failed", "error")
                ui.label("Invalid cells are highlighted red - hover for the reason. Edit cells directly "
                         "and the row is re-validated.").classes("text-gray-500 text-sm")
                val_grid = ui.aggrid({"columnDefs": [], "rowData": []}).classes("w-full h-80")
                val_grid.on("cellValueChanged", lambda e: on_cell_edit(e.args))
                with ui.row():
                    ui.button("Download invalid rows", icon="file_download", on_click=lambda: download_invalid()
                              ).props("outline color=negative")
                    ai_fix_btn = ui.button("AI suggest fixes", icon="auto_awesome", on_click=lambda: ai_fix()
                                           ).props("outline color=secondary")
                with ui.stepper_navigation():
                    ui.button("Back", on_click=stepper.previous).props("flat")
                    run_next = ui.button("Next: send valid rows", icon="send", on_click=lambda: go_run())

            # Step 4 - run & results
            with ui.step("Send & results", icon="rocket_launch"):
                with ui.row().classes("items-end"):
                    conc = ui.number("Concurrency", value=5, min=1, max=50).classes("w-32")
                    timeout = ui.number("Timeout (s)", value=30, min=1).classes("w-32")
                    attempts = ui.number("Attempts per call", value=3, min=1, max=10).classes("w-40")
                    backoff = ui.number("Backoff (s)", value=0.5, min=0, step=0.5).classes("w-32")
                with ui.row().classes("gap-4 items-center"):
                    sent_total = stat_card("Total", "total", "summarize")
                    sent_ok = stat_card("Success", "success", "check_circle")
                    sent_fail = stat_card("Failed", "failed", "cancel")
                    sent_pending = stat_card("Pending", "pending", "hourglass_top")
                    chart = ui.echart({
                        "tooltip": {"trigger": "item"},
                        "series": [{"type": "pie", "radius": ["50%", "75%"], "label": {"show": False},
                                    "data": [], "color": ["#10b981", "#e11d48", "#f59e0b"]}],
                    }).classes("w-48 h-40")
                progress = ui.linear_progress(value=0, show_value=False).props("rounded size=12px color=primary")
                with ui.row():
                    run_btn = ui.button("Run", icon="play_arrow", on_click=lambda: run(False)).props(
                        "unelevated size=lg")
                    retry_btn = ui.button("Retry failed", icon="replay", on_click=lambda: run(True)).props(
                        "unelevated color=warning")
                    ui.button("Success.xlsx", icon="download",
                              on_click=lambda: download_results(CallStatus.SUCCESS)).props("outline color=positive")
                    ui.button("Failed.xlsx", icon="download",
                              on_click=lambda: download_results(CallStatus.FAILED)).props("outline color=negative")
                    ai_explain_btn = ui.button("AI explain failures", icon="auto_awesome",
                                               on_click=lambda: ai_explain()).props("outline color=secondary")
                insights = ui.column().classes("w-full")
                results_grid = ui.aggrid({
                    "columnDefs": [
                        {"field": "row", "headerName": "Row", "width": 80},
                        {"field": "status", "width": 110,
                         "cellClassRules": {"text-positive font-bold": "x == 'success'",
                                            "text-negative font-bold": "x == 'failed'"}},
                        {"field": "code", "headerName": "HTTP", "width": 90},
                        {"field": "attempts", "width": 100},
                        {"field": "error", "flex": 1},
                        {"field": "response", "flex": 2},
                    ],
                    "rowData": [],
                    "rowSelection": {"mode": "multiRow"},
                }).classes("w-full h-80")
                ui.button("Retry selected rows", icon="replay", on_click=lambda: retry_selected()).props("flat")
                with ui.stepper_navigation():
                    ui.button("Back", on_click=stepper.previous).props("flat")
                    ui.button("Start over", icon="restart_alt", on_click=lambda: ui.navigate.reload()).props("flat")

    ai_enabled = services.ai().enabled
    for b in (ai_map_btn, ai_fix_btn, ai_explain_btn):
        b.set_visibility(ai_enabled)

    # ----- step 1
    def choose_template(name: str) -> None:
        s.template = templates[name]
        fields_info.clear()
        with fields_info:
            for f in s.template.fields:
                ui.chip(f"{f.name}: {f.type}{'' if f.required else ' (optional)'}",
                        color="primary" if f.required else "grey").props("outline dense")
        next1.set_enabled(bool(s.table.rows))

    async def on_upload(e) -> None:
        s.file_bytes, s.file_name = await e.file.read(), e.file.name
        try:
            s.table = read_table(s.file_bytes, s.file_name)
        except Exception as exc:
            ui.notify(f"Could not read file: {exc}", type="negative")
            return
        sheet_select.options = s.table.sheets
        sheet_select.value = s.table.sheet
        sheet_select.set_visibility(len(s.table.sheets) > 1)
        show_preview()

    def load_sheet(sheet: str) -> None:
        if s.file_bytes and sheet and sheet != s.table.sheet:
            s.table = read_table(s.file_bytes, s.file_name, sheet)
            show_preview()

    def show_preview() -> None:
        file_label.text = f"{s.file_name}: {len(s.table.rows)} rows, {len(s.table.columns)} columns"
        preview.options["columnDefs"] = [{"field": c, "headerName": c} for c in s.table.columns]
        preview.options["rowData"] = [_jsonable(r) for r in s.table.rows[:100]]
        preview.update()
        preview.set_visibility(True)
        next1.set_enabled(bool(s.template and s.table.rows))

    def go_mapping() -> None:
        if not s.template:
            ui.notify("Choose a template", type="warning")
            return
        do_auto_map()
        render_mapping()
        stepper.next()

    # ----- step 2
    def do_auto_map() -> None:
        s.mapping = auto_map(s.table.columns, s.template.fields)

    def render_mapping() -> None:
        options = [NONE] + usable_columns(s.table.columns)
        mapping_box.clear()
        with mapping_box:
            for f in s.template.fields:
                with ui.row().classes("w-full items-center no-wrap"):
                    ui.icon("check_circle" if s.mapping.get(f.name) else
                            ("error" if f.required else "radio_button_unchecked"),
                            color="positive" if s.mapping.get(f.name) else ("negative" if f.required else "grey"))
                    ui.label(f.name).classes("w-56 font-medium")
                    ui.badge(f.type, color="accent").props("outline")
                    if f.required:
                        ui.badge("required", color="secondary").props("outline")
                    ui.icon("arrow_forward", color="grey")
                    ui.select(options, value=s.mapping.get(f.name) or NONE,
                              on_change=lambda e, f=f: set_map(f.name, e.value)).classes("w-72").props("dense outlined")
        render_header_report()

    def set_map(field: str, column: str) -> None:
        s.mapping[field] = None if column == NONE else column
        render_mapping()

    def render_header_report() -> None:
        rep = validate_headers(s.table.columns, s.mapping, s.template.fields)
        header_report.clear()
        with header_report:
            if rep.missing_required:
                with ui.card().classes("w-full bg-red-50 border-l-4 border-red-500"):
                    ui.label("Missing required columns (expected by the JSON format):").classes(
                        "text-red-700 font-bold")
                    with ui.row():
                        for name in rep.missing_required:
                            ui.chip(name, icon="error", color="negative")
            if rep.unused_columns:
                with ui.row().classes("items-center"):
                    ui.label("Unused columns:").classes("text-gray-500")
                    for c in rep.unused_columns:
                        ui.chip(c, color="grey").props("outline dense")
            if rep.ok:
                ui.label("All required fields are mapped.").classes("text-positive font-medium")

    async def ai_map() -> None:
        ai_map_btn.props("loading")
        try:
            sugg = await services.ai().suggest_mapping(
                usable_columns(s.table.columns), [f.name for f in s.template.fields],
                [_jsonable(r) for r in s.table.rows[:5]])
        except AiError as exc:
            ui.notify(str(exc), type="negative")
            return
        finally:
            ai_map_btn.props(remove="loading")
        valid_cols = set(s.table.columns)
        for item in sugg.items:
            if item.field in s.mapping and item.column in valid_cols and item.confidence >= 0.5:
                s.mapping[item.field] = item.column
        render_mapping()
        ui.notify("AI mapping applied - review before continuing", type="info")

    def go_validate() -> None:
        if not validate_headers(s.table.columns, s.mapping, s.template.fields).ok:
            ui.notify("Map all required fields first", type="negative")
            return
        revalidate()
        stepper.next()

    # ----- step 3
    def revalidate() -> None:
        s.validations = validate_rows(s.table.rows, s.mapping, s.template.fields)
        total_lbl.text, valid_lbl.text, invalid_lbl.text = (
            str(len(s.validations)), str(s.valid_count), str(s.invalid_count))
        run_next.set_enabled(s.valid_count > 0)
        render_validation_grid()

    def render_validation_grid() -> None:
        col_to_field = {c: f for f, c in s.mapping.items() if c}
        defs = [{"field": "__row", "headerName": "#", "width": 70, "pinned": "left"},
                {"field": "__status", "headerName": "Status", "width": 100, "pinned": "left",
                 "cellClassRules": {"text-positive": "x == 'valid'", "text-negative font-bold": "x == 'invalid'"}}]
        for c in s.table.columns:
            field = col_to_field.get(c)
            d = {"field": c, "headerName": c + (f" → {field}" if field else ""), "editable": True}
            if field:
                key = json.dumps(field)
                d["cellClassRules"] = {"cell-error": f"data.__errors && data.__errors[{key}]"}
                d[":tooltipValueGetter"] = f"p => p.data.__errors && p.data.__errors[{key}]"
            defs.append(d)
        rows = []
        for v in s.validations:
            row = _jsonable(s.table.rows[v.index])
            row.update(__row=v.index + 2, __status="valid" if v.valid else "invalid", __errors=v.errors,
                       __index=v.index)
            rows.append(row)
        rows.sort(key=lambda r: r["__status"] == "valid")  # invalid first
        val_grid.options.update(columnDefs=defs, rowData=rows, tooltipShowDelay=200)
        val_grid.update()

    def on_cell_edit(args: dict) -> None:
        data = args.get("data") or {}
        idx = data.get("__index")
        col = args.get("colId")
        if idx is None or col not in s.table.columns:
            return
        s.table.rows[idx][col] = args.get("newValue")
        revalidate()

    def download_invalid() -> None:
        if not s.invalid_count:
            ui.notify("No invalid rows", type="positive")
            return
        ui.download.content(write_invalid_rows(s.table.columns, s.table.rows, s.mapping, s.validations),
                            "Invalid.xlsx")

    async def ai_fix() -> None:
        col_of = s.mapping
        invalid = [{"row_index": v.index, "field": f, "value": s.table.rows[v.index].get(col_of.get(f) or ""),
                    "error": msg, "expected_type": next(x.type for x in s.template.fields if x.name == f)}
                   for v in s.validations for f, msg in v.errors.items()]
        if not invalid:
            ui.notify("Nothing to fix", type="positive")
            return
        ai_fix_btn.props("loading")
        try:
            result = await services.ai().suggest_fixes(invalid)
        except AiError as exc:
            ui.notify(str(exc), type="negative")
            return
        finally:
            ai_fix_btn.props(remove="loading")
        if not result.fixes:
            ui.notify("AI found no confident fixes", type="info")
            return
        with ui.dialog() as dlg, ui.card().classes("w-[720px]"):
            ui.label("AI suggested fixes").classes("text-lg font-bold")
            checks = []
            for fx in result.fixes:
                col = col_of.get(fx.field)
                if col is None or not 0 <= fx.row_index < len(s.table.rows):
                    continue
                old = s.table.rows[fx.row_index].get(col)
                checks.append((ui.checkbox(f"Row {fx.row_index + 2} · {fx.field}: {old!r} → {fx.suggested_value!r}"
                                           f"  ({fx.reason})", value=True), fx, col))

            def apply() -> None:
                for cb, fx, col in checks:
                    if cb.value:
                        s.table.rows[fx.row_index][col] = fx.suggested_value
                dlg.close()
                revalidate()

            with ui.row():
                ui.button("Apply selected", icon="check", on_click=apply)
                ui.button("Cancel", on_click=dlg.close).props("flat")
        dlg.open()

    def go_run() -> None:
        s.job = create_job(s.template, s.table.columns, s.mapping, s.table.rows, s.validations)
        update_progress()
        stepper.next()

    # ----- step 4
    def options() -> RunOptions:
        return RunOptions(concurrency=int(conc.value or 5), timeout_seconds=float(timeout.value or 30),
                          retry=RetryPolicy(max_attempts=int(attempts.value or 1),
                                            backoff_seconds=float(backoff.value or 0)))

    def update_progress() -> None:
        job = s.job
        if not job:
            return
        total, ok, fail, pend = len(job.rows), job.success_count, job.failed_count, job.pending_count
        sent_total.text, sent_ok.text, sent_fail.text, sent_pending.text = map(str, (total, ok, fail, pend))
        progress.value = (total - pend) / total if total else 0
        chart.options["series"][0]["data"] = [
            {"name": "Success", "value": ok}, {"name": "Failed", "value": fail}, {"name": "Pending", "value": pend}]
        chart.update()
        results_grid.options["rowData"] = [
            {"row": r.row_index + 2, "index": r.row_index, "status": r.result.status.value, "code": r.result.http_code,
             "attempts": r.result.attempts, "error": r.result.error, "response": r.result.response_text[:300]}
            for r in job.rows]
        results_grid.update()

    async def run(only_failed: bool) -> None:
        if not s.job or s.running:
            return
        if only_failed and not s.job.failed_count:
            ui.notify("No failed rows to retry", type="info")
            return
        s.running = True
        run_btn.props("loading")
        retry_btn.props("loading")
        timer = ui.timer(0.3, update_progress)
        try:
            await services.run(s.job, options(), only_failed=only_failed)
        finally:
            timer.cancel()
            s.running = False
            run_btn.props(remove="loading")
            retry_btn.props(remove="loading")
            update_progress()
        ui.notify(f"Done: {s.job.success_count} success, {s.job.failed_count} failed",
                  type="positive" if not s.job.failed_count else "warning")

    async def retry_selected() -> None:
        if not s.job or s.running:
            return
        selected = {r["index"] for r in await results_grid.get_selected_rows()}
        rows = [r for r in s.job.rows if r.row_index in selected]
        if not rows:
            ui.notify("Select rows in the results table first", type="info")
            return
        s.running = True
        timer = ui.timer(0.3, update_progress)
        sender = services.sender(s.job.template.auth)
        try:
            await run_rows(s.job, rows, sender, options())
        finally:
            await sender.aclose()
            timer.cancel()
            s.running = False
            services.storage.save_job(s.job)
            update_progress()

    def download_results(status: CallStatus) -> None:
        if not s.job:
            return
        count = s.job.success_count if status == CallStatus.SUCCESS else s.job.failed_count
        if not count:
            ui.notify(f"No {status.value} rows", type="info")
            return
        ui.download.content(write_results(s.job, status), f"{status.value.capitalize()}.xlsx")

    async def ai_explain() -> None:
        if not s.job or not s.job.failed_count:
            ui.notify("No failures to explain", type="info")
            return
        failures = [{"row_index": r.row_index, "http_code": r.result.http_code, "error": r.result.error,
                     "response": r.result.response_text[:500], "values": r.values}
                    for r in s.job.rows if r.result.status == CallStatus.FAILED]
        ai_explain_btn.props("loading")
        try:
            result = await services.ai().explain_failures(failures)
        except AiError as exc:
            ui.notify(str(exc), type="negative")
            return
        finally:
            ai_explain_btn.props(remove="loading")
        insights.clear()
        with insights, ui.card().classes("w-full border-l-4 border-pink-500"):
            ui.label(result.summary).classes("font-medium")
            for g in result.groups:
                with ui.row().classes("items-start"):
                    ui.badge(str(g.count), color="negative")
                    with ui.column().classes("gap-0"):
                        ui.label(g.cause).classes("font-bold")
                        ui.label(g.suggestion).classes("text-gray-600")



def _jsonable(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        out[k] = v if v is None or isinstance(v, (int, float, bool, str)) else str(v)
    return out
