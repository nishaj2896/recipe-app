"""A TCP proxy between the app and Postgres that can break the link on cue.

Each fault is one a production network really has:

- `latency`: every chunk waits this long, both ways (a slow or far database).
- `freeze()`: bytes stop moving but every socket stays open, as when a node
  or a firewall drops packets without a reset. Nothing tells the client;
  only its own timers can end the wait.
- `cut()`: every open connection is reset (SO_LINGER 0), as when Postgres is
  killed or fails over.
- `refuse()`: no listener, so a new connection is refused, as when the
  database is down. `listen_again()` brings it back.
- `cut_on(marker)` / `freeze_on(marker)`: the fault strikes when the app
  sends a query whose text holds `marker`, so it lands mid-request for
  certain, not between requests (where the pool's pre-ping would hide it).
  asyncpg sends a statement's text the first time it prepares it, so use a
  fresh engine, as each test's app has.

Not shared with the app code: a test helper only, run in the test's loop or
in a thread of its own for a server in another process.
"""

import asyncio
import contextlib
import socket
import struct
from dataclasses import dataclass, field

CHUNK = 65536


@dataclass(eq=False)
class _Link:
    client: asyncio.StreamWriter
    upstream: asyncio.StreamWriter
    tasks: list[asyncio.Task[None]] = field(default_factory=list)


class ChaosProxy:
    def __init__(self, upstream_host: str, upstream_port: int) -> None:
        self.upstream = (upstream_host, upstream_port)
        self.latency = 0.0
        self.port = 0
        self._flowing = asyncio.Event()
        self._flowing.set()
        self._links: set[_Link] = set()
        self._server: asyncio.Server | None = None
        self._trigger: tuple[bytes, str] | None = None
        self.triggered = asyncio.Event()

    @property
    def open_links(self) -> int:
        return len(self._links)

    async def start(self) -> None:
        """Listen on a free port, or on the same port again after refuse()."""
        self._server = await asyncio.start_server(
            self._accept, "127.0.0.1", self.port, reuse_address=True
        )
        self.port = self._server.sockets[0].getsockname()[1]

    def url(self, database_url: str) -> str:
        """`database_url` with its host and port pointed at the proxy."""
        from sqlalchemy.engine import make_url

        return (
            make_url(database_url)
            .set(host="127.0.0.1", port=self.port)
            .render_as_string(hide_password=False)
        )

    def cut_on(self, marker: bytes) -> None:
        self._trigger = (marker, "cut")

    def freeze_on(self, marker: bytes) -> None:
        self._trigger = (marker, "freeze")

    def freeze(self) -> None:
        self._flowing.clear()

    def restore(self) -> None:
        self._flowing.set()
        self._trigger = None
        self.latency = 0.0

    async def refuse(self) -> None:
        """Stop listening and reset every open connection."""
        server, self._server = self._server, None
        if server is not None:
            server.close()
        # Cut first: since Python 3.12 wait_closed() waits for every
        # connection the server accepted to finish.
        await self.cut()
        if server is not None:
            await server.wait_closed()

    async def listen_again(self) -> None:
        self.restore()
        if self._server is None:
            await self.start()

    async def cut(self) -> None:
        for link in list(self._links):
            await self._close(link, reset=True)

    async def close(self) -> None:
        await self.refuse()

    async def _accept(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            up_reader, up_writer = await asyncio.open_connection(*self.upstream)
        except OSError:
            _reset(writer)
            return
        link = _Link(client=writer, upstream=up_writer)
        self._links.add(link)
        link.tasks = [
            asyncio.create_task(self._pump(reader, up_writer, link, from_app=True)),
            asyncio.create_task(self._pump(up_reader, writer, link, from_app=False)),
        ]

    async def _pump(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        link: _Link,
        *,
        from_app: bool,
    ) -> None:
        try:
            while data := await reader.read(CHUNK):
                if from_app and self._fires(data) == "cut":
                    await self._close(link, reset=True)
                    return
                if self.latency:
                    await asyncio.sleep(self.latency)
                await self._flowing.wait()
                writer.write(data)
                await writer.drain()
        except (OSError, asyncio.CancelledError):
            pass
        finally:
            # One side closed: close the other, as a real hop would.
            if link in self._links:
                asyncio.get_running_loop().call_soon(
                    lambda: asyncio.ensure_future(self._close(link, reset=False))
                )

    def _fires(self, data: bytes) -> str | None:
        if self._trigger is None or self._trigger[0] not in data:
            return None
        action = self._trigger[1]
        self._trigger = None
        self.triggered.set()
        if action == "freeze":
            self.freeze()
        return action

    async def _close(self, link: _Link, *, reset: bool) -> None:
        if link not in self._links:
            return
        self._links.discard(link)
        for writer in (link.client, link.upstream):
            if reset:
                _reset(writer)
            else:
                writer.close()
        current = asyncio.current_task()
        for task in link.tasks:
            if task is not current:
                task.cancel()
        for task in link.tasks:
            if task is not current:
                with contextlib.suppress(asyncio.CancelledError, OSError):
                    await task


def _reset(writer: asyncio.StreamWriter) -> None:
    """Close with an RST, not a FIN: the peer sees ECONNRESET at once."""
    sock = writer.get_extra_info("socket")
    if sock is not None:
        with contextlib.suppress(OSError):
            sock.setsockopt(
                socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0)
            )
    writer.transport.abort()
