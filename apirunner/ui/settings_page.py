"""Settings page: AI key/model and storage location."""

from __future__ import annotations

from nicegui import ui

from apirunner.infra.ai import DEFAULT_MODEL
from apirunner.services import AI_KEY_SETTING, AI_MODEL_SETTING, services
from apirunner.ui.theme import frame


def page() -> None:
    st = services.storage
    with frame("/settings", "Settings", "AI assistance is optional - everything else works without it."):
        with ui.card().classes("soft-card w-full max-w-2xl"):
            with ui.row().classes("items-center"):
                ui.icon("auto_awesome", color="secondary", size="28px")
                ui.label("AI assistant (Claude)").classes("text-lg font-bold")
                status = ui.badge("", color="positive")
            ui.label("Used for smart column mapping, template generation, fix suggestions and failure insights. "
                     "Only headers and up to 5 sample rows are sent, never the whole file.").classes(
                "text-gray-500 text-sm")
            key = ui.input("Anthropic API key", value=st.get_setting(AI_KEY_SETTING), password=True,
                           password_toggle_button=True).classes("w-full")
            model = ui.input("Model", value=st.get_setting(AI_MODEL_SETTING) or DEFAULT_MODEL).classes("w-full")
            ui.label("Leave the key empty to use the ANTHROPIC_API_KEY environment variable.").classes(
                "text-gray-400 text-xs")

            def save() -> None:
                st.set_setting(AI_KEY_SETTING, key.value.strip())
                st.set_setting(AI_MODEL_SETTING, model.value.strip())
                refresh()
                ui.notify("Settings saved", type="positive")

            def refresh() -> None:
                enabled = services.ai().enabled
                status.text = "enabled" if enabled else "disabled"
                status.props(f"color={'positive' if enabled else 'grey'}")

            ui.button("Save", icon="save", on_click=save).props("unelevated")
            refresh()

        with ui.card().classes("soft-card w-full max-w-2xl"):
            ui.label("Storage").classes("text-lg font-bold")
            ui.label(f"Database: {st.path}").classes("font-mono text-sm")
            ui.label("Set APIRUNNER_DATA_DIR to change the location.").classes("text-gray-400 text-xs")
