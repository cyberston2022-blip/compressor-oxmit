"""Thin async client for the SVT Encore JobManager REST API."""

from __future__ import annotations

import httpx

from .log import get_logger

log = get_logger("oxmit.encore")


class EncoreError(Exception):
    pass


class EncoreClient:
    def __init__(self, base_url: str, user: str, password: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            auth=(user, password) if password else None,
            timeout=httpx.Timeout(30.0, connect=10.0),
            trust_env=False,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def health(self) -> dict:
        try:
            r = await self._client.get("/actuator/health", timeout=8.0)
        except httpx.HTTPError as exc:
            raise EncoreError(f"health request failed: {exc}") from exc
        if r.status_code != 200:
            raise EncoreError(f"health returned {r.status_code}")
        return r.json()

    async def queue_count(self) -> int:
        try:
            r = await self._client.get("/queueCount", timeout=8.0)
        except httpx.HTTPError as exc:
            raise EncoreError(f"queueCount failed: {exc}") from exc
        if r.status_code != 200:
            raise EncoreError(f"queueCount returned {r.status_code}")
        try:
            return int(r.json())
        except (TypeError, ValueError) as exc:
            raise EncoreError(f"queueCount bad body: {r.text[:200]}") from exc

    async def submit_job(
        self,
        *,
        profile: str,
        output_folder: str,
        base_name: str,
        input_uri: str,
        external_id: str,
        priority: int = 50,
        callback_uri: str | None = None,
        profile_params: dict | None = None,
        input_params: dict | None = None,
        segment_length: float | None = None,
    ) -> str:
        body: dict = {
            "profile": profile,
            "outputFolder": output_folder,
            "baseName": base_name,
            "externalId": external_id,
            "priority": priority,
            "inputs": [{"type": "AudioVideo", "uri": input_uri}],
        }
        if input_params:
            body["inputs"][0]["params"] = {k: str(v) for k, v in input_params.items()}
        if profile_params:
            body["profileParams"] = {k: str(v) for k, v in profile_params.items()}
        if segment_length:
            body["segmentLength"] = segment_length
        if callback_uri:
            body["progressCallbackUri"] = callback_uri
        try:
            r = await self._client.post("/encoreJobs", json=body)
        except httpx.HTTPError as exc:
            raise EncoreError(f"submit request failed: {exc}") from exc
        if r.status_code not in (200, 201):
            raise EncoreError(f"submit returned {r.status_code}: {r.text[:300]}")
        data = r.json()
        job_id = data.get("id")
        if not job_id:
            raise EncoreError(f"submit response missing id: {r.text[:300]}")
        return str(job_id)

    async def get_job(self, job_id: str) -> dict:
        try:
            r = await self._client.get(f"/encoreJobs/{job_id}")
        except httpx.HTTPError as exc:
            raise EncoreError(f"get_job request failed: {exc}") from exc
        if r.status_code == 404:
            raise EncoreNotFound(job_id)
        if r.status_code != 200:
            raise EncoreError(f"get_job returned {r.status_code}: {r.text[:200]}")
        return r.json()

    async def cancel_job(self, job_id: str) -> bool:
        try:
            r = await self._client.post(f"/encoreJobs/{job_id}/cancel")
        except httpx.HTTPError as exc:
            raise EncoreError(f"cancel request failed: {exc}") from exc
        if r.status_code in (200, 202, 204):
            return True
        if r.status_code == 409:
            return False  # already terminal
        raise EncoreError(f"cancel returned {r.status_code}: {r.text[:200]}")


class EncoreNotFound(EncoreError):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"job {job_id} not found (expired?)")
        self.job_id = job_id
