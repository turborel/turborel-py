"""Tests of connecting by settings, to servers of the test's own on Unix sockets."""

from __future__ import annotations

import shutil
import socket
import sys
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote

import pytest
from tests.kit import error, frame, ready, status

from turborel import OperationalError
from turborel._codec.frames import HEADER_BYTES, decode_header
from turborel.client import Options, Settings

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="the servers here listen on Unix sockets"
)

Script = list[bytes]
"""What a server of the test's sends, a reply to each request it reads in turn."""


def read_frame(peer: socket.socket) -> bytes | None:
    """A frame the client sent, its kind and body; None at the end."""
    head = b""
    while len(head) < HEADER_BYTES:
        chunk = peer.recv(HEADER_BYTES - len(head))
        if not chunk:
            return None
        head += chunk
    _, length = decode_header(head)
    body = b""
    while len(body) < length:
        body += peer.recv(length - len(body))
    return head + body


class Server:
    """A server on a Unix socket, answering each connection by a script."""

    def __init__(self, path: Path, scripts: list[Script]) -> None:
        """Listen at `path`, the connections answered by `scripts` in turn."""
        self.path = str(path)
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(self.path)
        self.listener.listen()
        self.scripts = scripts
        self.seen: list[list[int]] = []
        self.thread = threading.Thread(target=self._serve)
        self.thread.start()

    def _serve(self) -> None:
        for script in self.scripts:
            peer, _ = self.listener.accept()
            kinds: list[int] = []
            self.seen.append(kinds)
            with peer:
                for reply in script:
                    request = read_frame(peer)
                    if request is None:
                        break
                    kinds.append(request[0])
                    peer.sendall(reply)
                while (request := read_frame(peer)) is not None:
                    kinds.append(request[0])

    def close(self) -> None:
        """Stop listening, once every script ran."""
        self.thread.join(timeout=10)
        self.listener.close()


@pytest.fixture
def serve() -> Iterator[Callable[[str, list[Script]], Server]]:
    """Servers of scripts, closed after the test, in a short directory of their own.

    A Unix socket's path is short, so not under pytest's temporary
    directory, which on macOS is long.
    """
    root = Path(tempfile.mkdtemp(prefix="trl", dir="/tmp"))
    made: list[Server] = []

    def make(name: str, scripts: list[Script]) -> Server:
        server = Server(root / name, scripts)
        made.append(server)
        return server

    yield make
    for server in made:
        server.close()
    shutil.rmtree(root)


def uri(*paths: str, query: str = "") -> str:
    """A URI of ANN at the local sockets `paths`."""
    hosts = ",".join(quote(p, safe="") for p in paths)
    return f"turborel://ANN@{hosts}/?{query}"


def settings(text: str) -> Settings:
    """The settings of `text`, with no environment."""
    return Settings.resolve_in(Options.from_uri(text), lambda _: None)


TOLD_READ_WRITE = status("SERVER_READ_ONLY", "NO") + ready(capabilities=("status",))
TOLD_READ_ONLY = status("SERVER_READ_ONLY", "YES") + ready(capabilities=("status",))


def test_the_first_server_kept(serve: Callable[[str, list[Script]], Server]) -> None:
    """Verifies: [CLIENT Several servers] a server unreachable passed for the next.

    [CLIENT Connecting by settings] with no password, trust; over a local
    socket, no TLS [CLIENT TLS by mode]; the role told by
    SERVER_READ_ONLY: a replica passed for `target=read-write`, a server
    alone for `read-only`, and with none kept, each and why (08001).
    """
    good = serve("good", [[TOLD_READ_WRITE]])
    conn = settings(uri("/no/such/socket", good.path)).connect()
    assert conn.authorization == "ANN"
    conn.close()
    replica = serve("replica", [[TOLD_READ_ONLY], [TOLD_READ_ONLY]])
    primary = serve("primary", [[TOLD_READ_WRITE]] * 4)
    settings(
        uri(replica.path, primary.path, query="target=read-write")
    ).connect().close()
    settings(
        uri(primary.path, replica.path, query="target=read-only")
    ).connect().close()
    with pytest.raises(OperationalError) as none:
        settings(uri(primary.path, primary.path, query="target=read-only")).connect()
    assert none.value.sqlstate == "08001"
    assert none.value.message == (
        f"no server was kept: {primary.path}: the server is read-write, and read-only"
        f" is asked; {primary.path}: the server is read-write, and read-only is asked"
    )


def test_a_role_asked_of_replicas(serve: Callable[[str, list[Script]], Server]) -> None:
    """Verifies: [CLIENT Several servers] a role untold asked of REPLICAS.

    No such table, a server alone, read-write; a row PRIMARY read-write;
    the query its own transaction.
    """
    no_table = error(-103, "42000", "table INFORMATION_SCHEMA.REPLICAS is not defined")
    alone = serve("alone", [[ready(), no_table]])
    settings(uri(alone.path, query="target=read-write")).connect().close()
    assert alone.seen[0][:2] == [ord("H"), ord("Q")]
    lost = serve("lost", [[ready(), frame("E", b"")]])
    with pytest.raises(OperationalError):
        settings(uri(lost.path, query="target=read-write")).connect()


def test_channel_binding_required_of_settings_that_cannot_bind(
    serve: Callable[[str, list[Script]], Server],
) -> None:
    """Verifies: [CLIENT TLS by mode] `channel_binding` `require` refused (28000).

    No password, or one over a local socket, binds nothing; nothing is
    sent the server.
    """
    server = serve("bound", [[]])
    with pytest.raises(OperationalError) as refused:
        settings(uri(server.path, query="channel_binding=require")).connect()
    assert refused.value.sqlstate == "28000"
    server.close()
    assert server.seen == [[]]
