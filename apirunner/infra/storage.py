"""SQLite persistence for templates, jobs and settings."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from apirunner.core.models import Job, RequestTemplate

SCHEMA = """
CREATE TABLE IF NOT EXISTS templates (name TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY, template_name TEXT, created_at TEXT,
    total INTEGER, success INTEGER, failed INTEGER, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
"""


def default_db_path() -> Path:
    base = Path(os.environ.get("APIRUNNER_DATA_DIR", Path.home() / ".apirunner"))
    base.mkdir(parents=True, exist_ok=True)
    return base / "apirunner.db"


class Storage:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = str(path or default_db_path())
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    # Templates
    def save_template(self, t: RequestTemplate) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO templates VALUES (?, ?)", (t.name, t.model_dump_json()))

    def list_templates(self) -> list[RequestTemplate]:
        with self._conn() as c:
            rows = c.execute("SELECT data FROM templates ORDER BY name").fetchall()
        return [RequestTemplate.model_validate_json(r[0]) for r in rows]

    def get_template(self, name: str) -> RequestTemplate | None:
        with self._conn() as c:
            row = c.execute("SELECT data FROM templates WHERE name = ?", (name,)).fetchone()
        return RequestTemplate.model_validate_json(row[0]) if row else None

    def delete_template(self, name: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM templates WHERE name = ?", (name,))

    # Jobs
    def save_job(self, job: Job) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?)",
                (job.id, job.template.name, job.created_at, len(job.rows), job.success_count,
                 job.failed_count, job.model_dump_json()),
            )

    def list_jobs(self, limit: int = 200) -> list[dict]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, template_name, created_at, total, success, failed FROM jobs "
                "ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        keys = ["id", "template", "created_at", "total", "success", "failed"]
        return [dict(zip(keys, r)) for r in rows]

    def get_job(self, job_id: str) -> Job | None:
        with self._conn() as c:
            row = c.execute("SELECT data FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return Job.model_validate_json(row[0]) if row else None

    def delete_job(self, job_id: str) -> None:
        with self._conn() as c:
            c.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

    # Settings
    def get_setting(self, key: str, default: str = "") -> str:
        with self._conn() as c:
            row = c.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._conn() as c:
            c.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))

    def export_templates(self) -> str:
        return json.dumps([t.model_dump() for t in self.list_templates()], indent=2)

    def import_templates(self, text: str) -> int:
        items = json.loads(text)
        for item in items if isinstance(items, list) else [items]:
            self.save_template(RequestTemplate.model_validate(item))
        return len(items) if isinstance(items, list) else 1
