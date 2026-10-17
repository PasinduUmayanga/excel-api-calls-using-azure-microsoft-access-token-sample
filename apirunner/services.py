"""Application services: wires core logic to infrastructure. The UI only talks to this module."""

from __future__ import annotations

import os
from functools import cached_property

from apirunner.core.executor import ProgressCallback, retry_failed, run_job
from apirunner.core.models import AuthConfig, Job, RunOptions
from apirunner.infra.ai import AiAssistant
from apirunner.infra.http_client import HttpSender
from apirunner.infra.storage import Storage

AI_KEY_SETTING = "anthropic_api_key"
AI_MODEL_SETTING = "ai_model"


class AppServices:
    def __init__(self, storage: Storage | None = None) -> None:
        self._storage = storage

    @cached_property
    def storage(self) -> Storage:
        return self._storage or Storage()

    def ai(self) -> AiAssistant:
        key = self.storage.get_setting(AI_KEY_SETTING) or os.environ.get("ANTHROPIC_API_KEY", "")
        model = self.storage.get_setting(AI_MODEL_SETTING) or None
        return AiAssistant(api_key=key, model=model)

    @staticmethod
    def sender(auth: AuthConfig) -> HttpSender:
        return HttpSender(auth)

    async def run(self, job: Job, options: RunOptions, on_progress: ProgressCallback | None = None,
                  only_failed: bool = False) -> Job:
        sender = self.sender(job.template.auth)
        try:
            runner = retry_failed if only_failed else run_job
            await runner(job, sender, options, on_progress)
        finally:
            await sender.aclose()
            self.storage.save_job(job)
        return job


services = AppServices()
