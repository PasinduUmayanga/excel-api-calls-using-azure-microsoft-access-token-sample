"""History page: past bulk jobs, re-download results, retry failures."""

from __future__ import annotations

from nicegui import ui

from apirunner.core.models import CallStatus, RunOptions
from apirunner.infra.excel_io import write_results
from apirunner.services import services
from apirunner.ui.theme import frame


def page() -> None:
    with frame("/history", "History", "Every bulk run is saved. Download results again or retry failed rows."):
        with ui.card().classes("soft-card w-full"):
            grid = ui.aggrid({
                "columnDefs": [
                    {"field": "created_at", "headerName": "Date", "flex": 1},
                    {"field": "template", "headerName": "Template", "flex": 1},
                    {"field": "total", "width": 100},
                    {"field": "success", "width": 110, "cellClass": "text-positive font-bold"},
                    {"field": "failed", "width": 100, "cellClass": "text-negative font-bold"},
                    {"field": "id", "headerName": "Job ID", "width": 140},
                ],
                "rowData": [],
                "rowSelection": {"mode": "singleRow"},
            }).classes("w-full h-96")
            with ui.row():
                ui.button("Success.xlsx", icon="download", on_click=lambda: download(CallStatus.SUCCESS)).props(
                    "outline color=positive")
                ui.button("Failed.xlsx", icon="download", on_click=lambda: download(CallStatus.FAILED)).props(
                    "outline color=negative")
                retry_btn = ui.button("Retry failed", icon="replay", on_click=lambda: retry()).props(
                    "unelevated color=warning")
                ui.button("Delete", icon="delete", on_click=lambda: delete()).props("flat color=negative")

    def load() -> None:
        grid.options["rowData"] = services.storage.list_jobs()
        grid.update()

    async def selected_job():
        rows = await grid.get_selected_rows()
        if not rows:
            ui.notify("Select a job first", type="info")
            return None
        return services.storage.get_job(rows[0]["id"])

    async def download(status: CallStatus) -> None:
        job = await selected_job()
        if job:
            ui.download.content(write_results(job, status), f"{status.value.capitalize()}-{job.id}.xlsx")

    async def retry() -> None:
        job = await selected_job()
        if not job:
            return
        if not job.failed_count:
            ui.notify("This job has no failed rows", type="info")
            return
        retry_btn.props("loading")
        try:
            await services.run(job, RunOptions(), only_failed=True)
        finally:
            retry_btn.props(remove="loading")
        ui.notify(f"Retried: {job.success_count} success, {job.failed_count} failed",
                  type="positive" if not job.failed_count else "warning")
        load()

    async def delete() -> None:
        job = await selected_job()
        if job:
            services.storage.delete_job(job.id)
            load()

    load()
