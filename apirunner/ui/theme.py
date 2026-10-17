"""Shared look and feel: colour palette, page frame and small reusable widgets."""

from __future__ import annotations

from contextlib import contextmanager

from nicegui import app, ui

NAV = [
    ("/", "bolt", "Single Call"),
    ("/templates", "data_object", "JSON Templates"),
    ("/bulk", "table_view", "Excel Bulk"),
    ("/history", "history", "History"),
    ("/settings", "settings", "Settings"),
]

CSS = """
.gradient-header { background: linear-gradient(90deg, #4f46e5 0%, #9333ea 50%, #db2777 100%); }
.stat-card { border-radius: 16px; color: white; min-width: 160px; }
.stat-success { background: linear-gradient(135deg, #10b981, #059669); }
.stat-failed  { background: linear-gradient(135deg, #f43f5e, #be123c); }
.stat-pending { background: linear-gradient(135deg, #f59e0b, #d97706); }
.stat-total   { background: linear-gradient(135deg, #6366f1, #4338ca); }
.soft-card { border-radius: 16px; }
.cell-error { background-color: #fecaca !important; color: #7f1d1d; }
.nav-active { background: rgba(147, 51, 234, .12); color: #7c3aed; font-weight: 600; }
"""


def apply_colors() -> None:
    ui.colors(primary="#7c3aed", secondary="#db2777", accent="#06b6d4",
              positive="#10b981", negative="#e11d48", warning="#f59e0b", info="#3b82f6")
    ui.add_css(CSS)


@contextmanager
def frame(path: str, title: str, subtitle: str = ""):
    """Page layout: gradient header, navigation drawer, content column."""
    apply_colors()
    dark = ui.dark_mode(value=app.storage.general.get("dark", False))
    with ui.header(elevated=True).classes("gradient-header items-center px-4"):
        ui.button(icon="menu", on_click=lambda: drawer.toggle()).props("flat round color=white")
        ui.icon("rocket_launch", size="28px").classes("text-white")
        ui.label("API Runner").classes("text-xl font-bold text-white")
        ui.label("Generic API caller · Excel bulk · Retry · AI").classes("text-white/80 text-sm max-sm:hidden")
        ui.space()

        def toggle_dark() -> None:
            dark.toggle()
            app.storage.general["dark"] = dark.value

        ui.button(icon="dark_mode", on_click=toggle_dark).props("flat round color=white").tooltip("Dark mode")
    with ui.left_drawer(value=True, bordered=True).classes("p-2") as drawer:
        for href, icon, label in NAV:
            active = "nav-active" if href == path else ""
            with ui.link(target=href).classes(f"no-underline text-inherit rounded-lg w-full {active}"):
                with ui.row().classes("items-center gap-3 px-3 py-2"):
                    ui.icon(icon, size="22px")
                    ui.label(label)
    with ui.column().classes("w-full max-w-7xl mx-auto p-4 gap-4"):
        with ui.column().classes("gap-0"):
            ui.label(title).classes("text-2xl font-bold")
            if subtitle:
                ui.label(subtitle).classes("text-gray-500")
        yield


def stat_card(label: str, kind: str, icon: str) -> ui.label:
    """Coloured counter card; returns the label to update with the number."""
    with ui.card().classes(f"stat-card stat-{kind} p-4"):
        with ui.row().classes("items-center gap-3"):
            ui.icon(icon, size="32px")
            with ui.column().classes("gap-0"):
                value = ui.label("0").classes("text-3xl font-bold")
                ui.label(label).classes("text-sm opacity-90")
    return value


def status_badge(code: int | None) -> None:
    if code is None:
        color, text = "negative", "ERROR"
    elif code < 300:
        color, text = "positive", str(code)
    elif code < 400:
        color, text = "info", str(code)
    elif code < 500:
        color, text = "warning", str(code)
    else:
        color, text = "negative", str(code)
    ui.badge(text, color=color).classes("text-lg px-3 py-1")
