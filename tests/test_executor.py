import asyncio

from apirunner.core.executor import call_with_retry, create_job, retry_failed, run_job
from apirunner.core.models import (
    CallResult,
    CallStatus,
    FieldSpec,
    PreparedRequest,
    RequestTemplate,
    RetryPolicy,
    RunOptions,
)
from apirunner.core.validation import validate_rows

REQ = PreparedRequest(method="GET", url="https://x")


class FakeSender:
    """Returns queued status codes (None = network error); records calls."""

    def __init__(self, codes):
        self.codes = list(codes)
        self.calls = 0

    async def __call__(self, request, timeout):
        self.calls += 1
        code = self.codes.pop(0) if self.codes else 200
        return CallResult(status=CallStatus.FAILED, http_code=code, error="" if code else "ConnectError")


async def no_sleep(_):
    return None


def opts(attempts=3, **kw):
    return RunOptions(retry=RetryPolicy(max_attempts=attempts, backoff_seconds=0, **kw))


async def test_retries_on_5xx_then_succeeds():
    sender = FakeSender([503, 500, 200])
    result = await call_with_retry(sender, REQ, opts(), no_sleep)
    assert result.status == CallStatus.SUCCESS and result.attempts == 3


async def test_does_not_retry_client_errors():
    sender = FakeSender([400])
    result = await call_with_retry(sender, REQ, opts(), no_sleep)
    assert result.status == CallStatus.FAILED and result.attempts == 1 and result.error == "HTTP 400"


async def test_network_errors_retry_unless_disabled():
    assert (await call_with_retry(FakeSender([None, 200]), REQ, opts(), no_sleep)).status == CallStatus.SUCCESS
    result = await call_with_retry(FakeSender([None, 200]), REQ, opts(retry_on_network_error=False), no_sleep)
    assert result.status == CallStatus.FAILED and result.attempts == 1


async def test_gives_up_after_max_attempts_with_exponential_backoff():
    delays = []

    async def record(d):
        delays.append(d)

    options = RunOptions(retry=RetryPolicy(max_attempts=4, backoff_seconds=0.5))
    result = await call_with_retry(FakeSender([500] * 10), REQ, options, record)
    assert result.attempts == 4 and delays == [0.5, 1.0, 2.0]


def make_job(names):
    template = RequestTemplate(method="POST", url="https://x/{{name}}", fields=[FieldSpec(name="name")])
    rows = [{"Name": n} for n in names]
    mapping = {"name": "Name"}
    return create_job(template, ["Name"], mapping, rows, validate_rows(rows, mapping, template.fields))


def test_create_job_only_includes_valid_rows():
    job = make_job(["a", "", "c"])
    assert [r.row_index for r in job.rows] == [0, 2]


async def test_run_job_counts_and_retry_failed_reruns_only_failures():
    job = make_job(["ok1", "bad", "ok2"])

    async def sender(request, timeout):
        code = 500 if request.url.endswith("/bad") else 201
        return CallResult(status=CallStatus.FAILED, http_code=code)

    await run_job(job, sender, opts(attempts=1))
    assert (job.success_count, job.failed_count, job.pending_count) == (2, 1, 0)

    seen = []

    async def fixed(request, timeout):
        seen.append(request.url)
        return CallResult(status=CallStatus.FAILED, http_code=200)

    await retry_failed(job, fixed, opts(attempts=1))
    assert seen == ["https://x/bad"]
    assert (job.success_count, job.failed_count) == (3, 0)


async def test_concurrency_limit_is_respected():
    job = make_job([f"r{i}" for i in range(10)])
    active = peak = 0

    async def sender(request, timeout):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return CallResult(status=CallStatus.FAILED, http_code=200)

    await run_job(job, sender, RunOptions(concurrency=3))
    assert peak == 3 and job.success_count == 10


async def test_progress_callback_and_bad_template_fails_row_not_job():
    job = make_job(["a"])
    job.template.body = "{{name}}"
    job.template.method = "POST"
    updates = []

    async def boom(request, timeout):
        raise RuntimeError("sender must not raise, but if it does the row fails")

    await run_job(job, boom, opts(attempts=1), on_progress=lambda j: updates.append(j.pending_count))
    assert job.failed_count == 1 and "RuntimeError" in job.rows[0].result.error
    assert updates[0] == 1 and updates[-1] == 0

