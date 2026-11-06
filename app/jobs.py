"""In-memory job registry.

A job exists so the browser can show live progress ("PART-B aa gaya") instead of
staring at a spinner for 8 seconds, and so a slow sheet never blocks the HTTP
worker - the request returns a job id immediately and the work happens in the
event loop.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid

JOB_TTL = int(os.getenv("JOB_TTL", "600"))
MAX_STEPS = 24


class Job:
    __slots__ = ("id", "url", "ip", "status", "steps", "result", "error",
                 "created", "started", "finished", "done_event")

    def __init__(self, url: str, ip: str = ""):
        self.id = uuid.uuid4().hex[:16]
        self.url = url
        self.ip = ip
        self.status = "queued"      # queued | running | done | error
        self.steps: list[dict] = []
        self.result: dict | None = None
        self.error: dict | None = None
        self.created = time.time()
        self.started = 0.0
        self.finished = 0.0
        self.done_event = asyncio.Event()

    def finish(self) -> None:
        self.finished = time.time()
        try:
            self.done_event.set()
        except RuntimeError:
            pass

    def step(self, name: str, detail: str = "") -> None:
        if len(self.steps) >= MAX_STEPS:
            return
        self.steps.append({"t": round(time.time() - self.created, 2),
                           "name": name, "detail": detail})

    def to_dict(self, include_result: bool = True) -> dict:
        out = {
            "id": self.id,
            "status": self.status,
            "steps": self.steps,
            "elapsed": round((self.finished or time.time())
                             - (self.started or self.created), 2),
        }
        if include_result and self.result is not None:
            out["result"] = self.result
        if self.error:
            out["error"] = self.error
        return out


class JobStore:
    def __init__(self, ttl: int = JOB_TTL):
        self.ttl = ttl
        self._jobs: dict[str, Job] = {}

    def create(self, url: str, ip: str = "") -> Job:
        self._cleanup()
        job = Job(url, ip)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str):
        return self._jobs.get(job_id)

    def active_for(self, ip: str) -> int:
        return sum(1 for j in self._jobs.values()
                   if j.ip == ip and j.status in ("queued", "running"))

    def _cleanup(self) -> None:
        now = time.time()
        dead = [k for k, j in self._jobs.items()
                if now - (j.finished or j.created) > self.ttl]
        for k in dead:
            self._jobs.pop(k, None)
        if len(self._jobs) > 20000:          # hard cap, flood protection
            for k in sorted(self._jobs, key=lambda k: self._jobs[k].created)[:5000]:
                self._jobs.pop(k, None)

    def stats(self) -> dict:
        counts: dict[str, int] = {}
        for j in self._jobs.values():
            counts[j.status] = counts.get(j.status, 0) + 1
        return {"jobs": len(self._jobs), "by_status": counts}
