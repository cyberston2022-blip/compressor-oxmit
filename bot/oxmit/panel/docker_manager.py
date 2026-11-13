"""Docker container management and server resource telemetry interface.

Interacts with /var/run/docker.sock using docker-py wrapped in asyncio.to_thread.
Provides transparent mock fallback when docker.sock is unavailable (Windows dev,
isolated unit tests, or CI).
"""
from __future__ import annotations

import asyncio
import os
import shutil
import time
from typing import Any

from ..log import get_logger

log = get_logger("oxmit.panel.docker")

try:
    import psutil
except ImportError:
    psutil = None

_MOCK_CONTAINERS = [
    {"name": "oxmit-bot", "image": "oxmit/bot:local", "status": "running", "health": "healthy"},
    {"name": "oxmit-postgres", "image": "postgres:17-alpine", "status": "running", "health": "healthy"},
    {"name": "oxmit-redis", "image": "redis:8.6-alpine", "status": "running", "health": "healthy"},
    {"name": "oxmit-botapi", "image": "oxmit/telegram-bot-api:local", "status": "running", "health": "healthy"},
    {"name": "oxmit-encore-web", "image": "ghcr.io/svt/encore-web:1.0.0", "status": "running", "health": "healthy"},
    {"name": "oxmit-encore-worker-1", "image": "ghcr.io/svt/encore-worker:1.0.0", "status": "running", "health": "none"},
    {"name": "oxmit-encore-worker-2", "image": "ghcr.io/svt/encore-worker:1.0.0", "status": "running", "health": "none"},
]


def get_system_metrics(cfg: Any = None, state: Any = None) -> dict[str, Any]:
    """Retrieve host system resource metrics (CPU, RAM, Disk, Uptime, Load)."""
    # CPU percent (non-blocking sampler)
    cpu_pct = 0.0
    if psutil:
        try:
            cpu_pct = float(psutil.cpu_percent(interval=None))
        except Exception:
            cpu_pct = 0.0

    # RAM metrics
    if psutil:
        try:
            vm = psutil.virtual_memory()
            ram = {
                "total": int(vm.total),
                "used": int(vm.used),
                "percent": round(float(vm.percent), 1),
            }
        except Exception:
            ram = {"total": 0, "used": 0, "percent": 0.0}
    else:
        ram = {"total": 0, "used": 0, "percent": 0.0}

    # Disk metrics
    media_root = getattr(cfg, "media_root", "/") if cfg else "/"
    if not os.path.exists(media_root):
        media_root = "/"
    try:
        du = shutil.disk_usage(media_root)
        disk_pct = round(100.0 * du.used / du.total, 1) if du.total > 0 else 0.0
        disk = {
            "total": int(du.total),
            "used": int(du.used),
            "percent": disk_pct,
        }
    except Exception:
        disk = {"total": 0, "used": 0, "percent": 0.0}

    # Host uptime (seconds)
    uptime_s = 0.0
    if psutil and hasattr(psutil, "boot_time"):
        try:
            uptime_s = round(float(time.time() - psutil.boot_time()), 1)
        except Exception:
            pass
    if uptime_s <= 0.0 and state and hasattr(state, "started_at"):
        uptime_s = round(float(time.time() - state.started_at), 1)

    # Load average (1m, 5m, 15m)
    load_avg = [0.0, 0.0, 0.0]
    if hasattr(os, "getloadavg"):
        try:
            load_avg = [round(float(x), 2) for x in os.getloadavg()]
        except (OSError, AttributeError):
            pass
    if load_avg == [0.0, 0.0, 0.0] and psutil:
        try:
            cores = psutil.cpu_count() or 1
            est_load = round((cpu_pct / 100.0) * cores, 2)
            load_avg = [est_load, 0.0, 0.0]
        except Exception:
            pass

    return {
        "cpu": round(cpu_pct, 1),
        "ram": ram,
        "disk": disk,
        "uptime_s": uptime_s,
        "load_avg": load_avg,
    }


class DockerManager:
    """Manages Docker daemon interactions over the local Unix socket."""

    def __init__(self, socket_path: str = "/var/run/docker.sock") -> None:
        self.socket_path = socket_path
        self._client: Any = None
        self._mock_mode = False
        self.mock_ping_ok = True
        self._init_client()

    def _init_client(self) -> None:
        if os.getenv("OXMIT_DOCKER_MOCK") == "1" or not os.path.exists(self.socket_path):
            self._mock_mode = True
            log.info("DockerManager operating in mock fallback mode (socket absent or mock set)")
            return
        try:
            import docker

            self._client = docker.DockerClient(base_url=f"unix://{self.socket_path}")
            self._client.ping()
            self._mock_mode = False
            log.info("DockerManager connected successfully to %s", self.socket_path)
        except Exception as exc:
            log.warning("Docker SDK initialization failed; using mock mode: %s", str(exc)[:120])
            self._mock_mode = True

    async def ping(self) -> bool:
        """Check if Docker daemon is responsive."""
        if self._mock_mode or not self._client:
            return self.mock_ping_ok
        try:
            return await asyncio.to_thread(self._client.ping)
        except Exception:
            return False

    async def get_containers(self) -> list[dict[str, Any]]:
        """Query list of containers with status and health."""
        if self._mock_mode or not self._client:
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            return [
                {
                    "id": f"mock{i:08x}",
                    "name": c["name"],
                    "image": c["image"],
                    "status": c["status"],
                    "health": c["health"],
                    "created": now_iso,
                }
                for i, c in enumerate(_MOCK_CONTAINERS)
            ]

        def _sync_list() -> list[dict[str, Any]]:
            containers = []
            for c in self._client.containers.list(all=True):
                attrs = c.attrs
                state = attrs.get("State", {})
                health = (
                    state.get("Health", {}).get("Status", "none")
                    if "Health" in state
                    else "none"
                )
                img = (
                    c.image.tags[0]
                    if (c.image and c.image.tags)
                    else attrs.get("Config", {}).get("Image", "unknown")
                )
                containers.append(
                    {
                        "id": c.short_id,
                        "name": c.name.lstrip("/"),
                        "image": img,
                        "status": c.status,
                        "health": health,
                        "created": attrs.get("Created", ""),
                    }
                )
            containers.sort(key=lambda x: x["name"])
            return containers

        return await asyncio.to_thread(_sync_list)

    def _find_container_sync(self, name: str) -> Any:
        try:
            return self._client.containers.get(name)
        except Exception:
            # Match by name without leading slash or short_id
            for c in self._client.containers.list(all=True):
                if c.name.lstrip("/") == name or c.short_id == name:
                    return c
            raise KeyError(f"Container '{name}' not found")

    async def restart_container(self, name: str) -> dict[str, Any]:
        """Restart specified container.
        
        If restarting the bot container itself, schedules the restart after
        a 1.5s delay so the HTTP response completes cleanly first.
        """
        current_hostname = os.environ.get("HOSTNAME", "")
        valid_mock_names = {c["name"] for c in _MOCK_CONTAINERS}

        if self._mock_mode or not self._client:
            if name not in valid_mock_names and not any(name in c["name"] for c in _MOCK_CONTAINERS):
                raise KeyError(f"Container '{name}' not found")

            is_self = name in ("oxmit-bot", "bot") or (current_hostname and current_hostname in name)
            if is_self:
                async def _delayed_mock():
                    await asyncio.sleep(1.5)
                    log.info("Mock self-restart executed after delay")

                asyncio.create_task(_delayed_mock())
                return {
                    "status": "ok",
                    "container": name,
                    "message": "Container self-restart scheduled in 1.5s",
                }
            return {"status": "ok", "container": name}

        target = await asyncio.to_thread(self._find_container_sync, name)
        is_self = (
            name in ("oxmit-bot", "bot")
            or target.name.lstrip("/") in ("oxmit-bot", "bot")
            or (current_hostname and target.id.startswith(current_hostname))
        )

        if is_self:
            async def _delayed_restart() -> None:
                await asyncio.sleep(1.5)
                log.warning("Initiating delayed container self-restart for %s", target.name)
                try:
                    await asyncio.to_thread(target.restart, timeout=10)
                except Exception as exc:
                    log.exception("Delayed self-restart encountered error: %s", exc)

            asyncio.create_task(_delayed_restart())
            return {
                "status": "ok",
                "container": name,
                "message": "Container self-restart scheduled in 1.5s",
            }

        await asyncio.to_thread(target.restart, timeout=10)
        return {"status": "ok", "container": name}

    async def get_logs(self, name: str, tail: int = 100) -> str:
        """Fetch recent container logs with bounded tail."""
        tail = max(1, min(int(tail), 2000))
        valid_mock_names = {c["name"] for c in _MOCK_CONTAINERS}

        if self._mock_mode or not self._client:
            if name not in valid_mock_names and not any(name in c["name"] for c in _MOCK_CONTAINERS):
                raise KeyError(f"Container '{name}' not found")
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            return (
                f"[{now_iso}] [INFO] Simulated log stream for {name} (tail={tail})\n"
                f"[{now_iso}] [INFO] Container service nominal."
            )

        def _sync_logs() -> str:
            target = self._find_container_sync(name)
            raw = target.logs(tail=tail, stdout=True, stderr=True, timestamps=True)
            return raw.decode("utf-8", errors="replace")

        return await asyncio.to_thread(_sync_logs)
