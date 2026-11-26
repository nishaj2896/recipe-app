"""SIGTERM against the real server process (ADR-0013 rule 7).

Kubernetes sends SIGTERM, waits terminationGracePeriodSeconds (30 s by
default), then SIGKILL. `recipe-app serve` must stop taking connections,
let in-flight requests finish within SHUTDOWN_GRACE_SECONDS, and exit.
After a clean drain uvicorn re-raises the signal, so the process ends "by
SIGTERM" (Kubernetes shows exit code 143, the normal code for a stopped pod).
The proxy's latency keeps a real request in flight while the signal lands.
"""

import asyncio
import json
import os
import signal
import socket
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest

from recipe_app.domain.recipe import Recipe
from tests.chaos.conftest import KEY
from tests.chaos.proxy import ChaosProxy

pytestmark = pytest.mark.anyio

SERVE = Path(sys.executable).parent / "recipe-app"
STOPPED = -signal.SIGTERM


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class Server:
    def __init__(self, process: asyncio.subprocess.Process, port: int) -> None:
        self.process = process
        self.base = f"http://127.0.0.1:{port}"
        self.lines: list[dict[str, object]] = []

    async def read_logs(self) -> None:
        assert self.process.stdout is not None
        async for raw in self.process.stdout:
            text = raw.decode().strip()
            if text:
                self.lines.append(json.loads(text))

    def messages(self) -> list[str]:
        return [str(line["message"]) for line in self.lines]


@pytest.fixture
async def serve(proxy: ChaosProxy, seeded_database_url: str) -> AsyncIterator[object]:
    """Start `recipe-app serve` with the given grace; yields a starter."""
    started: list[tuple[Server, asyncio.Task[None]]] = []

    async def start(grace: int) -> Server:
        port = free_port()
        env = {
            **os.environ,
            "DATABASE_URL": proxy.url(seeded_database_url),
            "CURSOR_SIGNING_KEYS": json.dumps({"a": KEY}),
            "CURSOR_ACTIVE_KID": "a",
            "API_PORT": str(port),
            "SHUTDOWN_GRACE_SECONDS": str(grace),
            "REQUEST_TIMEOUT_SECONDS": "60",
            "LOG_FORMAT": "json",
        }
        process = await asyncio.create_subprocess_exec(
            str(SERVE),
            "serve",
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        server = Server(process, port)
        reader = asyncio.create_task(server.read_logs())
        started.append((server, reader))
        async with httpx.AsyncClient(base_url=server.base) as client:
            for _ in range(100):
                try:
                    if (await client.get("/healthz")).status_code == 200:
                        return server
                except httpx.TransportError:
                    pass
                await asyncio.sleep(0.1)
        raise AssertionError(f"server did not start: {server.messages()}")

    yield start
    for server, reader in started:
        if server.process.returncode is None:
            server.process.kill()
            await server.process.wait()
        await reader


async def test_sigterm_lets_the_request_in_flight_finish(
    serve: object, proxy: ChaosProxy, seed: tuple[Recipe, ...]
) -> None:
    server: Server = await serve(grace=10)  # type: ignore[operator]
    proxy.latency = 0.1  # a detail read takes a couple of seconds now
    async with httpx.AsyncClient(base_url=server.base, timeout=30) as client:
        in_flight = asyncio.create_task(client.get(f"/api/v1/recipes/{seed[0].id}"))
        await asyncio.sleep(0.5)
        server.process.send_signal(signal.SIGTERM)
        await asyncio.sleep(0.3)
        # A new connection is refused while the old request drains.
        with pytest.raises(httpx.ConnectError):
            await client.get("/healthz")
        response = await in_flight

    assert response.status_code == 200
    assert await asyncio.wait_for(server.process.wait(), timeout=10) == STOPPED


async def test_a_request_past_the_grace_is_cut_and_still_logged(
    serve: object, proxy: ChaosProxy, seed: tuple[Recipe, ...]
) -> None:
    """The process still exits in time, so Kubernetes never needs SIGKILL."""
    server: Server = await serve(grace=1)  # type: ignore[operator]
    proxy.latency = 0.5  # a detail read now takes several seconds
    loop = asyncio.get_running_loop()
    async with httpx.AsyncClient(base_url=server.base, timeout=30) as client:
        in_flight = asyncio.create_task(client.get(f"/api/v1/recipes/{seed[0].id}"))
        await asyncio.sleep(0.5)
        signalled = loop.time()
        server.process.send_signal(signal.SIGTERM)
        with pytest.raises(httpx.RemoteProtocolError):
            await in_flight
        code = await asyncio.wait_for(server.process.wait(), timeout=10)
        took = loop.time() - signalled

    assert code == STOPPED
    assert took < 4
    access = [line for line in server.lines if line["logger"] == "recipe_app.access"]
    cut = [
        line for line in access if line.get("route") == "/api/v1/recipes/{recipe_id}"
    ]
    assert len(cut) == 1, server.messages()
    assert cut[0]["error"] == "cancelled"
