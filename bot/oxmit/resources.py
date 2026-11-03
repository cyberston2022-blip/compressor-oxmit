"""Dynamic worker CPU allocation (user spec).

One active encode gets the whole machine (7 cores per worker); two concurrent
encodes split the budget (3.2 each); more jobs share what remains. The quota
is applied LIVE through the Docker socket (container.update) only when the
active count changes — no container recreation.

If the socket or the docker SDK is unavailable, the tuner disables itself and
Docker's fair-share scheduler distributes the static compose cap.
"""
from __future__ import annotations

import os

from .config import Settings
from .log import get_logger

log = get_logger("oxmit.resources")

CPU_PERIOD = 100000


def cores_for(active: int, single: float, multi: float, floor: float) -> float:
    """Per-worker core budget for `active` running jobs."""
    if active <= 1:
        return single
    if active == 2:
        return multi
    return max(floor, round(single / active, 2))


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
        """Apply the per-worker quota for `active` running jobs (debounced)."""
        import asyncio

        if self._disabled or active < 0:
            return
        target = cores_for(active, self.cfg.worker_cpu_single,
                           self.cfg.worker_cpu_multi, self.cfg.worker_cpu_min)
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
                    # The compose stack creates workers with NanoCPUs set, and
                    # the update API rejects mixing cpu_period with it — post
                    # the NanoCPUs field directly.
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
        if updated:
            log.info("worker CPU quota tuned", extra={
                "detail": f"active={active} cores={target} containers={updated}"})
            self._last = target
