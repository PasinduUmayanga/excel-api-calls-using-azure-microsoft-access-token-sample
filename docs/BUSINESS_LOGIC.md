# Business Logic

This document lists the rules the application follows. Each rule is implemented in `apirunner/core`
(pure functions, no I/O) and covered by the tests named in brackets.

## 1. Templates and placeholders (`core/template.py`) [test_template.py]

| Rule | Detail |
|---|---|
| Placeholder syntax | `{{name}}` or `{{name:type}}`. Names may contain letters, digits, `_ - . [ ]`. Spaces inside the braces are allowed |
| Types | `string` (default), `number`, `integer`, `boolean`, `date`, `array`, `object`. An unknown type is treated as `string` |
| Path parameters | `:name` directly after a `/` in the **path** of a URL. `http://host:8080` is never treated as a parameter |
| Field discovery | Placeholders are collected from the URL, then the body, then the headers, in order of first appearance. A name that appears several times becomes one field. Settings already made for a field (required, regex, …) are kept when fields are detected again |
| Sample → template | Plain JSON is turned into placeholders: strings → `{{path}}`, ints → `:integer`, floats → `:number`, bools → `:boolean`, lists → `:array`. Nested keys use dotted paths |

### Type conversion (`coerce`)
| Type | Accepts | Rejects |
|---|---|---|
| integer | `42`, `"42"`, `42.0` | `1.5`, `"twenty"`, booleans |
| number | any numeric value. A whole-number result becomes an int | text, booleans |
| boolean | `true/false/1/0/yes/no/y/n` (any case) | anything else |
| date | Excel dates, ISO `YYYY-MM-DD…` → `YYYY-MM-DD` | invalid dates |
| array | JSON array text, or comma-separated text → list | – |
| object | JSON object text | JSON that is not an object |
| string | anything. Excel numbers like `1234.0` become `"1234"` | – |

An empty cell (blank or whitespace) converts to `None`. Whether that is allowed is decided by
validation (§4).

### Rendering
- **URL**: placeholder values are URL-encoded (`a b` → `a%20b`, `/` → `%2F`). `:params` are replaced in
  the path only.
- **JSON body**: the body is parsed as JSON and each value is checked. A string that is *exactly* one
  placeholder is replaced by the typed value (`"{{age:integer}}"` → `31`). A placeholder inside a longer
  string is inserted as text.
- **Non-JSON body**: plain text substitution.
- **GET**: no body is ever sent.

## 2. Parameter binding (`core/binding.py`) [test_binding.py]

- `detect_param_names` lists the placeholder names in the URL (including `:params`), body and headers.
- `sync_params` keeps the parameter table in step with what the user types:
  - values already entered for placeholders that still exist are kept
  - a row is added for each new placeholder
  - rows for placeholders that were deleted are removed
  - parameters added by hand (query or header) are always kept
- `bind_single` / `build_request`:
  - **placeholder** parameters fill the matching `{{name}}`
  - **query** parameters become `?name=value`
  - **header** parameters become HTTP headers
- `to_curl` shows the exact request (without auth secrets) as a curl command.

## 3. Column mapping (`core/mapping.py`) [test_mapping_validation.py]

Each field is matched to at most one column, and each column is used at most once. Matching runs in
this order, and a later step only considers fields and columns that are still unmatched:

1. **Exact** name.
2. **Normalised** name: lower case with everything except a–z and 0–9 removed. The last part of a dotted
   field also counts (`address.city` ↔ `City`).
3. **Fuzzy**: RapidFuzz similarity ratio of at least 80, using the best remaining column.
4. **Containment**: the normalised field name is inside the column name or the other way round, with at
   least 3 characters (`name` ↔ `Full Name`).

Columns starting with `_` (the result columns added to exported files) are never matched. This is what
lets a Failed.xlsx file be uploaded again without changes.

## 4. Validation (`core/validation.py`) [test_mapping_validation.py]

**Header check:**
- `missing_required`: required fields with no column and no default. These **block** the run.
- `missing_optional`: optional fields with no column, or fields that have a default.
- `unused_columns`: columns that are not matched to any field (shown for information only).

**Row check**, for each field in order:
1. If the cell is empty, use the field's default. If there is no default and the field is required, the
   error is `required`. If the field is optional, the value is `None`.
2. Convert the value to the field type. On failure the error is `expected <type>, got <value>`.
3. Check the **allowed** values, if any. On failure the error is `must be one of: …`.
4. Check the **regex**, if any (`re.fullmatch` on the text form). On failure the error is
   `does not match pattern …`.

A row is valid only if no field has an error. **Only valid rows become part of a job.**

## 5. Execution and retry (`core/executor.py`) [test_executor.py]

- **Job**: the template, the columns, the mapping, and one `RowResult` per valid row. Each `RowResult`
  holds the original row, the converted values and the call result.
- **Concurrency**: an `asyncio.Semaphore(concurrency)` limits how many calls run at the same time.
- **Attempts**: `max_attempts` calls in total. A call succeeds when the HTTP code is 2xx.
- **Retry decision**:
  - a status code in `retry_on_status` (default `408, 429, 500, 502, 503, 504`) is retried
  - a network error or timeout is retried if `retry_on_network_error` is on (the default)
  - any other code, e.g. 400, 401, 404 or 422, is **not** retried
- **Backoff**: the wait before retry *n* is `backoff_seconds × 2^(n-1)`, e.g. 0.5 s, 1 s, 2 s.
- **Isolation**: if building or sending one row raises an error, only that row fails. The rest of the
  job carries on.
- **Retry failed**: runs only rows whose status is `failed`, and updates their results in place. Rows
  that already succeeded are never sent again.
- **Retry selected**: the same as retry failed, but for rows the user picks.
- **Counts**: success, failed and pending are calculated from the row statuses, so they are always
  consistent.
- **Persistence**: the job is saved to SQLite after every run or retry.

## 6. HTTP and authentication (`infra/http_client.py`) [test_http_storage_ai.py]

| Auth | Behaviour |
|---|---|
| Bearer | `Authorization: Bearer <token>`, unless the request already sets one |
| API key | Header `<name>: <value>`, or query parameter `?<name>=<value>` |
| Basic | `Authorization: Basic base64(user:pass)` |
| Azure AD | A client-credentials POST to `login.microsoftonline.com/{tenant}/oauth2/v2.0/token` (default scope `https://graph.microsoft.com/.default`). The token is cached per tenant, client and scope until 60 s before it expires |

The sender **never raises an exception**. Network, timeout and authentication errors come back as a
`CallResult` with `http_code=None` and the error message.

## 7. Result files (`infra/excel_io.py`) [test_excel_io.py]

| File | Contents |
|---|---|
| Excel template | Header row = field names, with a note on each header giving its type and whether it is required (plus the pattern and allowed values, if any). Allowed values appear as a dropdown |
| Success.xlsx / Failed.xlsx | The original columns (any old `_` columns removed), then `_status, _http_code, _error, _response, _attempts`. Result cells are green or red. Responses are cut to 32,000 characters |
| Invalid.xlsx | The original columns plus `_error` (`field: message; …`). Bad cells are red |

Files are read from the first sheet, or the sheet the user selects. Blank rows and columns without a
name are ignored. CSV files are read as UTF-8, with or without a BOM.

## 8. AI assistance (`infra/ai.py`) [test_http_storage_ai.py]

- **Optional**: AI is on only when an API key is set in Settings or `ANTHROPIC_API_KEY`. Without one, the
  UI hides every AI button.
- **Model**: `claude-opus-5-5` by default, configurable. Requests use **structured outputs**
  (`messages.parse` with a Pydantic schema), so every answer is a validated object. Effort is `low` to
  keep answers fast and cheap.
- **Data sent**:

  | Feature | What the AI receives |
  |---|---|
  | Mapping | Column names, field names and **at most 5 sample rows** |
  | Fixes | The invalid cells (at most 50) |
  | Failures | The failed rows (at most 50, responses cut to 500 characters) |
  | Response analysis | The request and the response (body cut to 12,000 characters) |
  | Request and template drafts | Only the text the user typed |

- **Safety**:
  - AI suggestions are never applied silently. A mapping is only applied when its confidence is at
    least 0.5, and the user still sees it.
  - Each suggested fix has a checkbox.
  - Request and template drafts fill the form for the user to review before anything is sent.
- **Errors**: an invalid key, rate limits, connection problems and refusals are all reported as an
  `AiError` with a readable message. They never break the page.

| Feature | Method | Output |
|---|---|---|
| Request from description | `request_from_prompt` | method, URL with placeholders, headers, params (placeholder/query/header), body, notes |
| Response analysis | `analyze_response` | outcome, summary, key points, key values, next steps |
| Template from sample | `template_from_sample` | method, URL, headers, body template, notes |
| Smart mapping | `suggest_mapping` | field → column, confidence, reason |
| Fix suggestions | `suggest_fixes` | row, field, suggested value, reason |
| Failure insights | `explain_failures` | summary plus groups (cause, count, rows, suggestion) |
