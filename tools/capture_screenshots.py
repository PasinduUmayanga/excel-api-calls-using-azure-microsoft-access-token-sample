"""Drive the real UI with Playwright against the local mock API and save screenshots to docs/images.

    python tools/capture_screenshots.py

Starts samples/mock_api.py and the app (web mode, throw-away data dir), seeds a demo template,
walks through every page and the full Excel bulk flow, then stops both servers.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import Page, expect, sync_playwright  # noqa: E402

from apirunner.core.models import FieldSpec, RequestTemplate  # noqa: E402
from apirunner.infra.storage import Storage  # noqa: E402

OUT = ROOT / "docs" / "images"
APP = "http://127.0.0.1:8765"
MOCK = "http://127.0.0.1:8099"


def wait_for(url: str, seconds: float = 30) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return
        except Exception as exc:  # 404 still means the server is up
            if getattr(exc, "code", None):
                return
            time.sleep(0.3)
    raise TimeoutError(url)


def seed(data_dir: str) -> None:
    st = Storage(Path(data_dir) / "apirunner.db")
    st.save_template(RequestTemplate(
        name="Create user", method="POST", url=f"{MOCK}/users",
        headers={"Accept": "application/json"},
        body='{\n  "name": "{{name}}",\n  "email": "{{email}}",\n  "age": "{{age:integer}}",\n'
             '  "address": { "city": "{{address.city}}" }\n}',
        fields=[FieldSpec(name="name"), FieldSpec(name="email", regex=r"[^@\s]+@[^@\s]+"),
                FieldSpec(name="age", type="integer"), FieldSpec(name="address.city", required=False)],
    ))
    st.set_setting("anthropic_api_key", os.environ.get("ANTHROPIC_API_KEY", "sk-ant-demo-key-for-screenshots"))


def shot(page: Page, name: str, full: bool = True) -> None:
    page.wait_for_timeout(600)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
    print("saved", name)


def run(page: Page) -> None:
    # Single call
    page.goto(f"{APP}/")
    page.get_by_label("Request URL").fill(f"{MOCK}/users/{{{{id}}}}")
    page.wait_for_timeout(500)
    page.get_by_label("Value").first.fill("7")
    page.get_by_role("button", name="Add parameter").click()
    names = page.get_by_label("Name")
    names.last.fill("verbose")
    page.get_by_label("Value").last.fill("true")
    shot(page, "01-single-call-params")
    page.get_by_role("button", name="Send").click()
    expect(page.get_by_text("Response", exact=True)).to_be_visible(timeout=15000)
    shot(page, "02-single-call-response")
    page.get_by_role("tab", name="Preview").click()
    shot(page, "03-single-call-preview", full=False)
    page.get_by_role("button", name="AI: describe the request").click()
    page.get_by_role("textbox").last.fill("Get user 42 from the demo API with verbose details")
    shot(page, "04-single-call-ai-dialog", full=False)
    page.keyboard.press("Escape")

    # Templates
    page.goto(f"{APP}/templates")
    page.get_by_role("button", name="Create user").click()
    page.wait_for_timeout(800)
    shot(page, "05-templates")

    # Bulk flow
    page.goto(f"{APP}/bulk")
    page.get_by_label("JSON template").click()
    page.get_by_role("option", name="Create user").click()
    page.locator("input[type=file]").set_input_files(str(ROOT / "samples" / "users.xlsx"))
    expect(page.get_by_text("users.xlsx: 8 rows")).to_be_visible(timeout=15000)
    shot(page, "06-bulk-upload")
    page.get_by_role("button", name="Next: map columns").click()
    page.wait_for_timeout(800)
    shot(page, "07-bulk-mapping")
    # Demonstrate header validation: un-map a required field, capture the warning, then restore it
    page.get_by_text("Full Name", exact=True).first.click()
    page.get_by_role("option", name="— not mapped —").click()
    page.wait_for_timeout(500)
    shot(page, "07b-bulk-missing-column")
    page.get_by_text("— not mapped —", exact=True).first.click()
    page.get_by_role("option", name="Full Name").click()
    page.wait_for_timeout(500)
    page.get_by_role("button", name="Next: validate").click()
    page.wait_for_timeout(1200)
    shot(page, "08-bulk-validation")
    page.get_by_role("button", name="Next: send valid rows").click()
    page.get_by_label("Backoff (s)").fill("0.1")
    page.get_by_role("button", name="Run").click()
    expect(page.get_by_text("Done:")).to_be_visible(timeout=60000)
    expect(page.get_by_text("Done:")).to_be_hidden(timeout=15000)  # let the toast disappear
    shot(page, "09-bulk-results")
    with page.expect_download() as dl:
        page.get_by_role("button", name="Failed.xlsx").click()
    dl.value.save_as(str(Path(tempfile.gettempdir()) / "Failed.xlsx"))  # proves the download works

    # History and settings
    page.goto(f"{APP}/history")
    page.wait_for_timeout(800)
    shot(page, "10-history")
    page.goto(f"{APP}/settings")
    shot(page, "11-settings")

    # Dark mode
    page.goto(f"{APP}/bulk")
    page.locator("header button").filter(has_text="dark_mode").click()
    page.goto(f"{APP}/templates")
    page.get_by_role("button", name="Create user").click()
    shot(page, "12-dark-mode", full=False)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    data_dir = tempfile.mkdtemp(prefix="apirunner-shots-")
    seed(data_dir)
    env = {**os.environ, "APIRUNNER_DATA_DIR": data_dir, "PYTHONPATH": str(ROOT)}
    procs = [
        subprocess.Popen([sys.executable, str(ROOT / "samples" / "mock_api.py")], env=env),
        subprocess.Popen([sys.executable, "-m", "apirunner", "--web", "--no-show", "--port", "8765"],
                         env=env, cwd=ROOT),
    ]
    try:
        wait_for(f"{MOCK}/users/1")
        wait_for(APP)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            run(page)
            browser.close()
    finally:
        for proc in procs:
            proc.terminate()


if __name__ == "__main__":
    main()
