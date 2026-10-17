# AGENTS.md: guide for AI coding agents and contributors

API Runner is a Python desktop and web app (NiceGUI). It calls any REST API, either one request at a
time with parameters filled in automatically, or in bulk from Excel with column matching, validation,
retry, Success/Failed exports and optional Claude AI help.

Read first: `README.md` (overview), `docs/ARCHITECTURE.md` (layers and modules),
`docs/BUSINESS_LOGIC.md` (rules you must keep). Folder-specific guides are in `apirunner/core/AGENTS.md`,
`apirunner/infra/AGENTS.md`, `apirunner/ui/AGENTS.md` and `tests/AGENTS.md`.

## Commands

```bash
python -m venv .venv && .venv\Scripts\activate     # macOS/Linux: source .venv/bin/activate
pip install -e ".[dev]"                            # app + test dependencies
pytest                                             # full suite (~10 s); must stay green
pytest --cov=apirunner                             # coverage
python -m apirunner --web --no-show --port 8765    # run headless for manual or e2e checks
python samples/mock_api.py                         # local demo API on :8099
python tools/capture_screenshots.py                # e2e walkthrough + refresh docs/images (needs: playwright install chromium)
```

## Layering rules (do not break)

- `apirunner/core`: **pure** logic and Pydantic models. No I/O, and no imports from `infra`, `ui`,
  `nicegui`, `httpx`, `openpyxl` or `anthropic`.
- `apirunner/infra`: adapters (HTTP, Excel, SQLite, AI). May import `core`, never `ui`.
- `apirunner/services.py`: composition root. The UI gets storage, AI, senders and runs from here.
- `apirunner/ui`: NiceGUI pages. No business rules here. If you are writing an `if` about data
  validity, it belongs in `core`.
- The executor receives HTTP through the `Sender` protocol. Keep it injectable so tests can pass fakes.

## Behaviour other code relies on

Changing any of these requires updating `docs/BUSINESS_LOGIC.md` and the tests:
- Placeholder syntax `{{name}}`, `{{name:type}}` and `:param`. A whole-string placeholder keeps the
  value's type.
- Columns starting with `_` are result columns and are **ignored** when matching. This is what makes
  `Failed.xlsx` re-uploadable.
- Only valid rows are sent. **Retry failed** never re-sends successful rows.
- Default retry: 3 attempts, on 408/429/5xx and network errors, with exponential backoff. Other 4xx
  codes are never retried.
- `HttpSender.__call__` never raises. Failures come back as a `CallResult`.
- AI is optional. Every AI button is hidden when `services.ai().enabled` is false. At most 5 sample rows
  are sent for mapping, and suggestions are never applied without the user seeing them.

## Conventions

- Python 3.11+, type hints everywhere, `from __future__ import annotations`.
- Pydantic v2 models for anything stored or passed between layers.
- Async for I/O (httpx, Anthropic `AsyncAnthropic`). The UI handlers are `async def` when they await.
- Lines up to 120 characters. Short docstrings on modules and public functions. Match the existing
  comment density (sparse).
- UI colours come from `ui/theme.py` (primary `#7c3aed`, secondary `#db2777`, accent `#06b6d4`). Reuse
  `frame()`, `stat_card()` and `status_badge()` rather than restyling.
- AI: use `AiAssistant._ask(prompt, PydanticModel)` (structured outputs via `messages.parse`). The default
  model is `claude-opus-5-5`, and the user can override it in Settings or with `APIRUNNER_AI_MODEL`.

## Definition of done

1. `pytest` passes. New logic in `core`/`infra` has unit tests, and new pages or buttons have a
   `tests/test_ui.py` check.
2. If the UI changed visibly, run `python tools/capture_screenshots.py` and commit the updated
   `docs/images`.
3. Update `docs/USER_MANUAL.md` for anything users see, and `docs/BUSINESS_LOGIC.md` for rule changes.
4. Do not commit `.venv/`, `*.db`, `.nicegui/` or real API keys.

## Roadmap ideas (not implemented yet)

- Package a Windows `.exe` with `nicegui-pack` and publish it from AppVeyor.
- Save auth secrets in the OS keyring instead of the template JSON.
- Rate limit (requests per second) as a run option; pause and cancel a running job.
- OpenAPI import that lists endpoints and creates templates.
- Multi-user web deployment (auth, Postgres storage, background workers).
- Theme the CodeMirror editors for dark mode.
