"""Tests of connecting for asyncio by settings, to servers of the test's own."""

from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote

import pytest
from tests.kit import error, ready, status
from tests.settings.test_connecting import Server

from turborel import OperationalError, aio
from turborel._aio import connect as aio_connect
from turborel.client import Options, Settings

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="the servers here listen on Unix sockets"
)

TOLD_READ_WRITE = status("SERVER_READ_ONLY", "NO") + ready(capabilities=("status",))
TOLD_READ_ONLY = status("SERVER_READ_ONLY", "YES") + ready(capabilities=("status",))


@pytest.fixture
def serve() -> Iterator[Callable[[str, list[list[bytes]]], Server]]:
    """Servers of scripts, in a short directory of their own."""
    root = Path(tempfile.mkdtemp(prefix="trl", dir="/tmp"))
    made: list[Server] = []

    def make(name: str, scripts: list[list[bytes]]) -> Server:
        server = Server(root / name, scripts)
        made.append(server)
        return server

    yield make
    for server in made:
        server.close()
    shutil.rmtree(root)


def uri(*paths: str, query: str = "") -> str:
    """A URI of ANN at the local sockets `paths`."""
    return "turborel://ANN@" + ",".join(quote(p, safe="") for p in paths) + f"/?{query}"


def test_connecting_for_asyncio(
    serve: Callable[[str, list[list[bytes]]], Server],
) -> None:
    """Verifies: [CLIENT Several servers] for asyncio, an unreachable server passed.

    [CLIENT Connecting by settings] trust over a local socket; the role
    told by SERVER_READ_ONLY, or asked of REPLICAS; none kept, each and
    why (08001); channel binding required of settings that cannot bind
    (28000).
    """
    good = serve("good", [[TOLD_READ_WRITE]])
    replica = serve("replica", [[TOLD_READ_ONLY]])
    no_table = error(-103, "42000", "table INFORMATION_SCHEMA.REPLICAS is not defined")
    alone = serve("alone", [[ready(), no_table]])
    lost = serve("lost", [[ready(), b"E" + bytes(4)]])
    bound = serve("bound", [[]])

    async def main() -> None:
        conn = await aio.connect(uri("/no/such/socket", good.path))
        conn.client.close()
        with pytest.raises(OperationalError) as none:
            await aio.connect(uri(replica.path, query="target=read-write"))
        assert none.value.message == "the server is read-only, and read-write is asked"
        settings = Settings.resolve_in(
            Options.from_uri(
                uri(alone.path, query="target=read-write&load_balance=random")
            ),
            lambda _: None,
        )
        client = await aio_connect.connect(settings)
        client.close()
        with pytest.raises(OperationalError):
            await aio.connect(uri(lost.path, query="target=read-write"))
        with pytest.raises(OperationalError) as unbound:
            await aio.connect(uri(bound.path, query="channel_binding=require"))
        assert unbound.value.sqlstate == "28000"
        with pytest.raises(OperationalError) as unreachable:
            await aio.connect(uri("/no/such/a", "/no/such/b"))
        assert unreachable.value.sqlstate == "08001"

    asyncio.run(main())
