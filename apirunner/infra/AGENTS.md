# infra/: adapters

Connects `core` to the outside world. May import `core`, never `ui`.

| File | Notes |
|---|---|
| `http_client.py` | `HttpSender` implements `core.executor.Sender`. **Never raise**: return a `CallResult` with `http_code=None` on errors. Auth is applied per attempt, and Azure tokens are cached in `AzureTokenProvider`. Always `await sender.aclose()` |
| `excel_io.py` | openpyxl/csv only. Result column names (`RESULT_COLUMNS`) are part of the re-upload contract, so do not rename them |
| `storage.py` | SQLite through the stdlib. The schema is created on start (`CREATE TABLE IF NOT EXISTS`). Add new columns with care, because existing user databases must keep working |
| `ai.py` | Claude through `anthropic.AsyncAnthropic().messages.parse(output_format=PydanticModel)`. Always go through `_ask()` so errors become `AiError`. Send only the minimum data (headers + ≤5 samples), and document any change in `docs/BUSINESS_LOGIC.md` §8 |

Tests: use `respx` for HTTP, `tmp_path` for SQLite, and a fake `messages.parse` for AI (see
`tests/test_http_storage_ai.py`). Never call real external services in tests.
