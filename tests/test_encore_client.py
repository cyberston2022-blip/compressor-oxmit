"""Tests for SVT Encore client methods and error handling."""
import httpx
import pytest

from oxmit.encore_client import EncoreClient, EncoreError, EncoreNotFound


@pytest.mark.asyncio
async def test_encore_health_ok():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "UP"})

    transport = httpx.MockTransport(handler)
    client = EncoreClient("http://mock", "user", "pass")
    client._client = httpx.AsyncClient(transport=transport, base_url="http://mock")

    data = await client.health()
    assert data["status"] == "UP"
    await client.aclose()


@pytest.mark.asyncio
async def test_encore_queue_count():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=4)

    transport = httpx.MockTransport(handler)
    client = EncoreClient("http://mock", "user", "pass")
    client._client = httpx.AsyncClient(transport=transport, base_url="http://mock")

    count = await client.queue_count()
    assert count == 4
    await client.aclose()


@pytest.mark.asyncio
async def test_encore_submit_job():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/encoreJobs"
        return httpx.Response(201, json={"id": "job-abc-123"})

    transport = httpx.MockTransport(handler)
    client = EncoreClient("http://mock", "user", "pass")
    client._client = httpx.AsyncClient(transport=transport, base_url="http://mock")

    jid = await client.submit_job(
        profile="balanced",
        output_folder="/out/1",
        base_name="out",
        input_uri="/in/1.mp4",
        external_id="1",
        profile_params={"crf": 23},
        input_params={"fflags": "+genpts"},
        segment_length=60.0,
    )
    assert jid == "job-abc-123"
    await client.aclose()


@pytest.mark.asyncio
async def test_encore_get_job_not_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="Not found")

    transport = httpx.MockTransport(handler)
    client = EncoreClient("http://mock", "user", "pass")
    client._client = httpx.AsyncClient(transport=transport, base_url="http://mock")

    with pytest.raises(EncoreNotFound) as exc_info:
        await client.get_job("missing-id")
    assert exc_info.value.job_id == "missing-id"
    await client.aclose()


@pytest.mark.asyncio
async def test_encore_cancel_job():
    def handler(request: httpx.Request) -> httpx.Response:
        if "terminal" in request.url.path:
            return httpx.Response(409, text="Already terminal")
        return httpx.Response(200, text="OK")

    transport = httpx.MockTransport(handler)
    client = EncoreClient("http://mock", "user", "pass")
    client._client = httpx.AsyncClient(transport=transport, base_url="http://mock")

    assert await client.cancel_job("active-id") is True
    assert await client.cancel_job("terminal-id") is False
    await client.aclose()
