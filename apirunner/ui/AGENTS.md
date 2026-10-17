# ui/: NiceGUI pages

One module per page, each with a `page()` function. Pages are registered in `apirunner/app.py`
(`ROUTES`) and added to the side menu in `theme.NAV`.

| File | Page |
|---|---|
| `single_call.py` | `/`: request builder, auto params, response viewer, AI request and response help |
| `templates_page.py` | `/templates`: template editor, fields grid, Excel template download, AI template |
| `bulk_page.py` | `/bulk`: 4-step stepper (upload → map → validate → run/results/retry) |
| `history_page.py` | `/history`: saved jobs, re-download, retry |
| `settings_page.py` | `/settings`: AI key and model, storage info |
| `theme.py` | colours, CSS, `frame()` layout, `stat_card()`, `status_badge()` |
| `widgets.py` | `AuthEditor`, `json_editor`, `parse_headers`, `pretty` |

Rules:
- Wrap page content in `with frame(path, title, subtitle):` so the header, menu and colours stay the same everywhere.
- Get data and actions from `apirunner.services.services`. Put rules in `core`, not here.
- Gate AI buttons with `.set_visibility(services.ai().enabled)` and catch `AiError` → `ui.notify(..., type="negative")`.
- Show long actions with `button.props("loading")` and remove it in `finally`.
- Give elements tests need a `.mark("name")`, and test with the NiceGUI `User` fixture (`tests/test_ui.py`).
- After visible changes, run `python tools/capture_screenshots.py` and update `docs/USER_MANUAL.md`.
  The script finds elements by label or button text, so update it if you rename them.
