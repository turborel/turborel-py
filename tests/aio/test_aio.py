"""Tests of turborel.aio over a peer of the test's own, its steps awaited."""

from __future__ import annotations

import asyncio
import sys

import pytest
from tests.kit import Peer, complete, description, error, frame, ready, rows, u32, u64

from turborel import IntegrityError, InterfaceError, OperationalError, aio
from turborel._aio.client import AsyncClient
from turborel._aio.connect import open_target
from turborel._aio.streams import AsyncStream
from turborel._auth.mechanisms import Trust
from turborel._session.capabilities import Offer
from turborel._transport.target import Local


def prepared(number: int, columns: int) -> bytes:
    """A Prepared of `number`, one BOOLEAN parameter, `columns` BOOLEAN columns."""
    body = u32(number) + u32(1) + b"\x00\x0e" + u32(columns)
    body += (b"\x01" + u32(1) + b"A" + b"\x0e\x00") * columns
    return frame("P", body)


async def opened(peer: Peer, *capabilities: str) -> AsyncClient:
    """An asyncio client logged in over `peer`."""
    peer.client.setblocking(False)  # noqa: FBT003  # asyncio's.
    reader, writer = await asyncio.open_connection(sock=peer.client)
    peer.reply(ready(capabilities=capabilities))
    client = AsyncClient(AsyncStream(reader, writer), None)
    await client.log_in("ANN", Trust(), Offer())
    client.set_read_timeout(5)
    peer.received()
    return client


def test_the_asyncio_interface_runs_the_same_requests() -> None:
    """Verifies: [DESIGN] D2 `turborel.aio`, the same objects, its waits coroutines.

    A cursor's execute, executemany and fetches; commit and rollback; the
    connection closed, its transaction rolled back first.
    """

    async def main() -> None:
        with Peer() as peer:
            conn = aio.Connection(await opened(peer, "row-counts"))
            cursor = conn.cursor()
            peer.reply(description("A"), rows((True,), (False,)), complete(active=True))
            await cursor.execute("SELECT A FROM T")
            assert (cursor.rowcount, await cursor.fetchone()) == (2, (True,))
            assert [r async for r in cursor] == [(False,)]
            assert await cursor.fetchmany() == []
            assert await cursor.fetchall() == []
            assert cursor.description is not None
            peer.reply(prepared(0, 0), complete(active=True, tail=b"\x06" + u64(1)))
            await cursor.execute("UPDATE T SET A = ?", (True,))
            assert cursor.rowcount == 1
            peer.reply(*[complete(active=True)] * 4)
            await cursor.executemany("UPDATE T SET A = ?", [(True,), (False,)])
            assert cursor.rowcount == -1
            await cursor.executemany("UPDATE T SET A = ?", [])
            peer.reply(
                error(-201, "23000", "dup", active=True),
                complete(),
                complete(),
                complete(),
            )
            with pytest.raises(IntegrityError):
                await cursor.executemany("UPDATE T SET A = ?", [(True,), (False,)])
            await conn.commit()
            await conn.rollback()
            conn.autocommit = True
            assert (conn.autocommit, conn.in_transaction) == (True, False)
            conn.autocommit = False
            cursor.setinputsizes(None)
            cursor.setoutputsize(1)
            async with cursor:
                pass
            with pytest.raises(InterfaceError):
                await cursor.execute("VALUES 1")
            peer.close()
            async with conn:
                pass
            assert conn.closed
            await conn.close()
            with pytest.raises(InterfaceError):
                conn.cursor()

    asyncio.run(main())


def test_the_asyncio_client() -> None:
    """Verifies: [DESIGN] D2 `turborel.aio` over the low-level client's requests.

    Ping, reset, a pipeline, a lost connection, Terminate's reply; a wait
    bounded by the read timeout.
    """

    async def main() -> None:
        with Peer() as peer:
            client = await opened(peer, "ping", "reset", "status")
            assert (client.granted, client.authorization, client.is_lost) == (
                ("ping", "reset", "status"),
                "ANN",
                False,
            )
            assert "AsyncClient" in repr(client)
            assert client.setting("NONE") is None
            assert (client.warning, client.last_generated, client.target) == (
                None,
                (),
                None,
            )
            peer.reply(frame("G"), complete())
            await client.ping()
            await client.reset()
            client.set_read_timeout(0.05)
            with pytest.raises(OperationalError):
                await client.query("VALUES 1")
            assert client.is_lost
            with pytest.raises(OperationalError):
                await client.terminate()
        with Peer() as peer:
            client = await opened(peer)
            peer.reply(error(-919, "08006", "ended"))
            peer.close()
            with pytest.raises(OperationalError, match="ended"):
                await client.terminate()
        with Peer() as peer:
            client = await opened(peer)
            peer.reply(rows())
            peer.close()
            with pytest.raises(OperationalError, match="answered Terminate"):
                await client.terminate()
        with Peer() as peer:
            client = await opened(peer)
            peer.close()
            await client.terminate()
            client.close()

    asyncio.run(main())


@pytest.mark.skipif(sys.platform != "win32", reason="only Windows has named pipes")
def test_a_named_pipe_for_asyncio() -> None:
    """Verifies: [CLIENT Connecting] on Windows, a named pipe for asyncio.

    The blocking pipe's reads and writes, each awaited in a thread of
    asyncio's.
    """
    import threading  # noqa: PLC0415  # Windows alone.
    from multiprocessing.connection import Listener  # noqa: PLC0415

    name = r"\\.\pipe\turborel-py-aio-test"

    async def main(listener: Listener) -> None:
        accepted: list[object] = []

        def serve() -> None:
            server = listener.accept()
            server.send_bytes(b"X" + (0).to_bytes(4, "little"))
            accepted.append(server)

        thread = threading.Thread(target=serve)
        thread.start()
        stream = await open_target(Local(name), 5.0)
        thread.join(timeout=10)
        assert await stream.read_frame(16) == (ord("X"), b"")
        await stream.write(b"")
        stream.close()
        for server in accepted:
            getattr(server, "close")()  # noqa: B009  # A Connection.

    with Listener(name, family="AF_PIPE") as listener:
        asyncio.run(main(listener))
