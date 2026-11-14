"""Dynamic worker CPU allocation (user spec).

One active encode gets the whole machine (7 cores per worker); two concurrent
encodes split the budget (3.2 each); more jobs share what remains. The quota
is applied LIVE through the Docker socket (container.update) only when the
active count changes — no container recreation.

If the socket or the docker SDK is unavailable, the tuner disables itself and
Docker's fair-share scheduler distributes the static compose cap.
"""
from __future__ import annotations

import asyncio
import os

from .config import Settings
from .log import get_logger

log = get_logger("oxmit.resources")


def cores_for(active: int, pool: float, replicas: int, floor: float) -> float:
    """Per-worker core budget (V3 §17: single source of truth).

    The tuner writes the SAME NanoCPU value to every worker replica, so the
    per-worker value must be capped at ``pool / replicas`` — otherwise the
    replicas collectively request ``single × replicas`` and overcommit the
    host (measured on Ohio: 3 × 4.5 = 13.5 requested on 8 vCPU dropped
    aggregate throughput from ~104 to ~74 FPS).

    Semantics:
    - ``pool``       = WORKER_CPU_SINGLE = TOTAL worker-pool CPU budget.
    - ``replicas``   = number of worker containers the tuner manages.
    - ``floor``      = WORKER_CPU_MIN — never allocate below this per worker.
    - ``WORKER_CPU_MULTI`` is advisory only (FFmpeg thread planning); the
      per-worker CPU cap is derived from the pool to make overcommit
      structurally impossible.
    """
    replicas = max(1, int(replicas))
    cap = pool / replicas
    if active <= 1:
        return round(cap, 2)
    shared = min(cap, pool / max(1, active))
    return round(max(shared, min(floor, cap)), 2)


class WorkerCpuTuner:
    def __init__(self, cfg: Settings) -> None:
        self.cfg = cfg
        self._last: float | None = None
        self._disabled = False
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        if self._disabled:
            return None
        if not os.path.exists(self.cfg.docker_socket):
            self._disabled = True
            log.warning("docker socket not found — dynamic CPU tuning disabled",
                        extra={"detail": self.cfg.docker_socket})
            return None
        try:
            import docker  # type: ignore

            self._client = docker.DockerClient(base_url=f"unix://{self.cfg.docker_socket}")
            return self._client
        except Exception as exc:  # noqa: BLE001
            self._disabled = True
            log.warning("docker SDK unavailable — dynamic CPU tuning disabled",
                        extra={"detail": str(exc)[:120]})
            return None

    async def tune(self, active: int) -> None:
        """Apply the per-worker quota for `active` running jobs (debounced).

        The target is capped at pool/replicas so the SUM across replicas can
        never exceed WORKER_CPU_SINGLE (overcommit guard, V3 §17).
        """
        if self._disabled or active < 0:
            return
        target = cores_for(active, self.cfg.worker_cpu_single,
                           len(self.cfg.worker_container_names),
                           self.cfg.worker_cpu_min)
        if self._last == target:
            return
        client = self._get_client()
        if client is None:
            return

        def _apply() -> int:
            updated = 0
            payload = {"NanoCPUs": int(target * 1e9)}
            for name in self.cfg.worker_container_names:
                try:
                    container = client.containers.get(name)
                    # DELIBERATE low-level API use (audit note: looks private,
                    # is load-bearing): docker-py 7.x update_container() does
                    # not expose NanoCPUs (only cpu_period/cpu_quota, which
                    # the update API rejects while compose-set NanoCPUs is in
                    # place). Posting the NanoCPUs field directly is the
                    # documented workaround, not an accident.
                    url = client.api._url(
                        "/containers/{0}/update".format(container.id))
                    res = client.api._post_json(url, data=payload)
                    client.api._raise_for_status(res)
                    updated += 1
                except Exception as exc:  # noqa: BLE001 - per-container best effort
                    log.warning("cpu quota update failed", extra={
                        "detail": f"{name}: {str(exc)[:100]}"})
            return updated

        updated = await asyncio.to_thread(_apply)
        # Mark the target applied only when EVERY worker got it: a partial
        # update must be retried on the next poll instead of being forgotten.
        if updated == len(self.cfg.worker_container_names):
            log.info("worker CPU quota tuned", extra={
                "detail": f"active={active} cores={target} containers={updated}"})
            self._last = target
