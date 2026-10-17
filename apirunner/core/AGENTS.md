# core/: domain logic (pure)

The rules of the app. **No I/O**: no network, files, database, UI or clock-dependent behaviour, except
`create_job`'s timestamp and id.

| File | Owns |
|---|---|
| `models.py` | All Pydantic models. Add fields with defaults so stored JSON (jobs and templates in SQLite) still loads |
| `template.py` | Placeholder regexes, `coerce()`, rendering. Keep `PLACEHOLDER_RE` and `PATH_PARAM_RE` the only parsers |
| `binding.py` | Parameter detection and sync, `build_request`, curl preview |
| `mapping.py` | `auto_map` order: exact → normalised → fuzzy (≥80) → containment. Keep `_` columns ignored |
| `validation.py` | Header and row validation. Error messages are shown to users and checked by tests |
| `executor.py` | Retry, backoff, concurrency, jobs. HTTP comes in only through the `Sender` protocol |

Rules:
- Every public function needs tests in `tests/`. Use fake senders and `sleep` stubs, never real HTTP or
  real waiting.
- When you change behaviour, update `docs/BUSINESS_LOGIC.md` in the same change.
- Keep functions deterministic and side-effect free (apart from mutating the `Job` passed into the executor).
