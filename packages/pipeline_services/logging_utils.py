"""Lightweight pipeline logging utilities.

Provides a ``LoggerAdapter`` that can bind a ``job_id`` so every log line
carries per-job context while remaining compatible with the standard library
``logging`` stack.
"""

from __future__ import annotations

import logging


class PipelineLoggerAdapter(logging.LoggerAdapter):
    """LoggerAdapter that prefixes messages with ``[job_id]`` when bound.

    ``bind()`` returns a new adapter instance, so adapters can be handed to
    concurrent workers without sharing mutable state.
    """

    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        job_id = self.extra.get("job_id")
        call_extra = kwargs.get("extra") or {}
        kwargs["extra"] = {**call_extra, **self.extra}
        if job_id:
            msg = f"[{job_id}] {msg}"
        return msg, kwargs

    def bind(self, job_id: str) -> "PipelineLoggerAdapter":
        """Return a new adapter bound to *job_id*."""
        return PipelineLoggerAdapter(self.logger, {**self.extra, "job_id": job_id})


def get_pipeline_logger(name: str) -> PipelineLoggerAdapter:
    """Factory: build a pipeline logger for *name* without a job binding."""
    return PipelineLoggerAdapter(logging.getLogger(name), {"job_id": ""})
