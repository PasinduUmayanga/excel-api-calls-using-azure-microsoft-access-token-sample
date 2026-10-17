# tests/

Run with `pytest` (config is in `pyproject.toml`: `asyncio_mode = "auto"`, so `async def test_...` works
without a decorator).

| File | Layer | Technique |
|---|---|---|
| `test_template.py`, `test_binding.py`, `test_mapping_validation.py` | core | plain unit tests, parametrised |
| `test_executor.py` | core | `FakeSender` with queued status codes, `no_sleep` stub, concurrency probe |
| `test_excel_io.py` | infra | in-memory workbooks, round trips (write → read → map → validate) |
| `test_http_storage_ai.py` | infra | `respx` HTTP mocks, `tmp_path` SQLite, fake `messages.parse` |
| `test_ui.py` | ui | NiceGUI `User` simulation (`pytest_plugins = ["nicegui.testing.user_plugin"]`). It runs `main.py`, which calls `register_pages()` |

Rules:
- No real network, no real AI calls, no sleeping. Tests must stay fast (whole suite about 10 s).
- UI tests get their own storage through the `isolated_storage` fixture (`APIRUNNER_DATA_DIR` + reset
  `services.storage`).
- The browser end-to-end walkthrough is `tools/capture_screenshots.py` (Playwright + `samples/mock_api.py`).
  It is not part of `pytest` because it needs Chromium.
