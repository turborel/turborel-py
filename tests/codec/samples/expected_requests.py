"""The request the driver sends for each client frame of the sample file.

Each entry builds, by the driver's own encoders, the request a sample's
meaning describes, by the sample's name [PROTOCOL Sample frames].
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from tests.codec.samples.expected_debug import REQUESTS as DEBUG

from turborel._codec import requests as q

if TYPE_CHECKING:
    from collections.abc import Callable

ANN: Final = ("ANN", "trust")
BIG: Final = "SELECT '" + "x" * 2000 + "' FROM T"
"""The Query `query-compressed` holds."""

EVERY: Final = ("status", "describe", "cursors", "compression", "declared-types")

REQUESTS: Final[dict[str, Callable[[], bytes]]] = {
    "hello-ping": lambda: q.Hello(*ANN, capabilities=("ping",)).encode(),
    "hello-none": lambda: q.Hello(*ANN).encode(),
    "hello-every": lambda: q.Hello(
        *ANN, capabilities=EVERY, attributes=(("application", "app"),)
    ).encode(),
    "hello-attribute-longest": lambda: q.Hello(
        *ANN, attributes=(("a" * 64, "v" * 1024),)
    ).encode(),
    "hello-attributes-most": lambda: q.Hello(
        *ANN, attributes=tuple((f"a{n}", "") for n in range(32))
    ).encode(),
    "hello-scram": lambda: q.Hello("ANN", "scram-sha-256", b"n,,n=,r=abc").encode(),
    "answer": lambda: q.Answer(b"c=biws,r=abc,p=xyz").encode(),
    "answer-empty": lambda: q.Answer(b"").encode(),
    "cancel": lambda: q.Cancel(b"\xa5" * 16).encode(),
    "query": lambda: q.Query("VALUES 1", ends=True).encode(),
    "query-empty": lambda: q.Query("").encode(),
    "query-attributes": lambda: q.Query(
        "VALUES QUERY_ATTRIBUTE('trace')", attributes=(("trace", "t1"),)
    ).encode(),
    "query-multi": lambda: q.Query(
        "VALUES 1; VALUES 2", ends=True, multi=True
    ).encode(),
    "prepare": lambda: q.Prepare(1, "SELECT K FROM T WHERE K > ?").encode(),
    "execute": lambda: q.Execute(1, (None, "", True), rows=2).encode(),
    "execute-cursor": lambda: q.Execute(
        1, (), rows=0, ends=True, attributes=(("a", "b"),), cursor=7
    ).encode(),
    "fetch": lambda: q.Fetch(1, rows=100).encode(),
    "fetch-cursor": lambda: q.Fetch(1, rows=0xFFFF_FFFF, cursor=7).encode(),
    "close": lambda: q.Close(1).encode(),
    "close-cursor": lambda: q.Close(1, cursor=7).encode(),
    "deallocate": lambda: q.Deallocate(0xFFFF_FFFF).encode(),
    "terminate": lambda: q.Terminate().encode(),
    "lob-read": lambda: q.LobRead(3, 0, 65536, characters=True).encode(),
    "lob-create": lambda: q.LobCreate(binary=True).encode(),
    "lob-append": lambda: q.LobAppend(4, b"\xc3").encode(),
    "lob-free": lambda: q.LobFree(4).encode(),
    "lob-hold": lambda: q.LobHold(3).encode(),
    "describe-statement": lambda: q.Describe(1).encode(),
    "describe-cursor": lambda: q.Describe(1, cursor=7).encode(),
    "ping": lambda: q.Ping().encode(),
    "reset": lambda: q.Reset().encode(),
    "change-user": lambda: q.ChangeUser("BOB", "password", b"secret").encode(),
    "copy-in": lambda: q.CopyIn("S.T", ("ID", "NAME"), ends=True).encode(),
    "copy-in-every-column": lambda: q.CopyIn("T").encode(),
    # Its values are character strings, as a copy of text sends them.
    "copy-data": lambda: q.CopyData((("1", None), ("2", "b"))).encode(),
    "copy-columns": lambda: q.CopyColumns((("1", "b"), (None, "")), 2).encode(),
    "copy-end": lambda: q.CopyEnd().encode(),
    "copy-end-abandon": lambda: q.CopyEnd(abandon=True).encode(),
    "query-compressed": lambda: q.Query(BIG, ends=True).encode(),
    **DEBUG,
}
"""Every client sample's request; of a compressed one, the frame it holds."""
