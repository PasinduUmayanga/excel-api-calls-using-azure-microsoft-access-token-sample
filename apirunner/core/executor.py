"""Run calls with retry/backoff and bounded concurrency. HTTP itself is injected (see infra.http_client)."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Any, Awaitable, Callable, Protocol

from .binding import build_request
from .models import CallResult, CallStatus, Job, PreparedRequest, RequestTemplate, RetryPolicy, RowResult, RunOptions
from .validation import RowValidation


class Sender(Protocol):
    """Performs exactly one HTTP attempt. Must not raise: network errors → http_code None + error."""

    def __call__(self, request: PreparedRequest, timeout: float) -> Awaitable[CallResult]: ...


ProgressCallback = Callable[[Job], None]
Sleep = Callable[[float], Awaitable[None]]


def is_success(code: int | None) -> bool:
    return code is not None and 200 <= code < 300


def should_retry(result: CallResult, policy: RetryPolicy) -> bool:
    if result.http_code is None:
        return policy.retry_on_network_error
    return result.http_code in policy.retry_on_status


async def call_with_retry(
    send: Sender, request: PreparedRequest, options: RunOptions, sleep: Sleep = asyncio.sleep
) -> CallResult:
    policy = options.retry
    attempts = max(1, policy.max_attempts)
    result = CallResult(status=CallStatus.FAILED)
    for attempt in range(1, attempts + 1):
        result = await send(request, options.timeout_seconds)
        result.attempts = attempt
        if is_success(result.http_code):
            result.status = CallStatus.SUCCESS
            return result
        result.status = CallStatus.FAILED
        if not result.error:
            result.error = f"HTTP {result.http_code}"
        if attempt < attempts and should_retry(result, policy):
            await sleep(policy.backoff_seconds * (2 ** (attempt - 1)))
            continue
        break
    return result


def create_job(
    template: RequestTemplate,
    columns: list[str],
    mapping: dict[str, str | None],
    source_rows: list[dict[str, Any]],
    validations: list[RowValidation],
) -> Job:
    """Create a job from the valid rows only."""
    rows = [
        RowResult(row_index=v.index, source=source_rows[v.index], values=v.values) for v in validations if v.valid
    ]
    return Job(
        id=uuid.uuid4().hex[:12],
        template=template,
        columns=columns,
        mapping=mapping,
        rows=rows,
        created_at=datetime.now().isoformat(timespec="seconds"),
    )


async def run_rows(
    job: Job,
    rows: list[RowResult],
    send: Sender,
    options: RunOptions,
    on_progress: ProgressCallback | None = None,
    sleep: Sleep = asyncio.sleep,
) -> Job:
    semaphore = asyncio.Semaphore(max(1, options.concurrency))

    async def one(row: RowResult) -> None:
        async with semaphore:
            try:
                request = build_request(job.template, row.values)
                row.result = await call_with_retry(send, request, options, sleep)
            except Exception as exc:  # bad template/URL must fail the row, not the job
                row.result = CallResult(status=CallStatus.FAILED, error=f"{type(exc).__name__}: {exc}", attempts=1)
            if on_progress:
                on_progress(job)

    for row in rows:
        row.result = CallResult(status=CallStatus.PENDING)
    if on_progress:
        on_progress(job)
    await asyncio.gather(*(one(r) for r in rows))
    return job


async def run_job(job: Job, send: Sender, options: RunOptions, on_progress: ProgressCallback | None = None) -> Job:
    return await run_rows(job, job.rows, send, options, on_progress)


async def retry_failed(job: Job, send: Sender, options: RunOptions, on_progress: ProgressCallback | None = None) -> Job:
    failed = [r for r in job.rows if r.result.status == CallStatus.FAILED]
    return await run_rows(job, failed, send, options, on_progress)
