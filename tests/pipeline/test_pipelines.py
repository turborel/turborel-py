"""Tests of pipelines over a peer of the test's own: windows, outcomes, skipping."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import pytest
from tests.kit import Peer, complete, description, error, frame, ready, rows

from turborel import IntegrityError, OperationalError
from turborel._pipeline.pipelines import (
    PIPELINE_WINDOW,
    Query,
    Savepoint,
    encoded,
    guarded,
    windows,
)
from turborel._session.state import Session
from turborel.client import SKIPPED, Complete, Connection, OnError, Rowset, Trust

if TYPE_CHECKING:
    import socket


def opened(peer: Peer) -> Connection:
    """A connection over `peer`."""
    peer.reply(ready())
    conn = Connection.open(peer.client, "ANN", Trust())
    peer.received()
    return conn


def test_requests_are_written_a_window_at_a_time() -> None:
    """Verifies: [CLIENT Pipelines] requests written a window of 64 KiB at a time.

    In order, a request longer than a window alone in one; every request
    each once; none queued, no window.
    """
    session = Session()
    queued = [
        Query("a"),
        Query("VALUES 1"),
        Query("x" * (PIPELINE_WINDOW // 2)),
        Query("y" * PIPELINE_WINDOW),
        Query("z"),
    ]
    found = windows(session, queued, ends=False)
    assert [len(w) for w in found] == [3, 1, 1]
    total = sum(len(f) for w in windows(session, queued, ends=True) for _, f in w)
    assert total == sum(len(encoded(session, q, ends=True)) for q in queued)
    assert windows(session, [], ends=False) == []
    assert guarded([Query("a"), Query("b")]) == [Query("a"), Savepoint(1), Query("b")]


def test_one_outcome_each_in_order() -> None:
    """Verifies: [CLIENT Pipelines] one outcome each, in order.

    [PROTOCOL Requests] a request sent before the last is answered, the
    replies read in turn; a failure its request's own, those after it
    run; under autocommit each request its own transaction.
    """
    with Peer() as peer:
        conn = opened(peer)
        conn.autocommit = True
        peer.reply(
            description("A"),
            rows((True,)),
            complete(),
            error(-201, "23000", "duplicate"),
            complete(tail=b"\x06" + bytes([1]) + bytes(7)),
        )
        outcomes = (
            conn.pipeline()
            .query("SELECT A FROM T")
            .query("INSERT 1")
            .query("INSERT 2")
            .run()
        )
        assert isinstance(outcomes[0], Rowset)
        assert isinstance(outcomes[1], IntegrityError)
        assert isinstance(outcomes[2], Complete)
        kinds = [peer.received() for _ in range(3)]
        assert all(kind == ord("Q") and body.endswith(b"\x01") for kind, body in kinds)


def test_skip_on_error() -> None:
    """Verifies: [CLIENT Pipelines] skip on error, savepoints.

    Those after a failure rolled back and skipped; a skipping batch one
    transaction, committed as it ends under autocommit where it began
    none.
    """
    with Peer() as peer:
        conn = opened(peer)
        conn.autocommit = True
        peer.reply(
            complete(active=True),
            complete(active=True),
            error(-201, "23000", "duplicate", active=True),
            complete(active=True),
            complete(active=True),
            complete(active=True),
            complete(active=True),
            complete(active=True),
            complete(),
        )
        pipeline = conn.pipeline().on_error(OnError.SKIP)
        outcomes = pipeline.query("INSERT 1").query("INSERT 2").query("INSERT 3").run()
        assert isinstance(outcomes[0], Complete)
        assert isinstance(outcomes[1], IntegrityError)
        assert outcomes[2] is SKIPPED
        sent = [peer.received()[1] for _ in range(8)]
        texts = [body[4 : 4 + body[0]].decode() for body in sent]
        assert texts == [
            "INSERT 1",
            "SAVEPOINT TURBOREL_PIPELINE_1",
            "INSERT 2",
            "SAVEPOINT TURBOREL_PIPELINE_2",
            "INSERT 3",
            "ROLLBACK TO SAVEPOINT TURBOREL_PIPELINE_2",
            "RELEASE SAVEPOINT TURBOREL_PIPELINE_1",
            "COMMIT",
        ]
        assert all(body.endswith(b"\x00") for body in sent)


def test_a_window_after_a_failure_is_never_sent() -> None:
    """Verifies: [CLIENT Pipelines] skip on error: those not yet written never sent.

    A request whose window follows the failure's is skipped unsent.
    """
    with Peer() as peer:
        conn = opened(peer)
        peer.reply(error(-201, "23000", "duplicate", active=True))
        drained: list[bytes] = []
        server = getattr(peer, "_server")  # noqa: B009  # Its end, read here alone.
        reader = threading.Thread(
            target=lambda: drained.append(drain(server, PIPELINE_WINDOW))
        )
        reader.start()
        pipeline = conn.pipeline().on_error(OnError.SKIP)
        outcomes = pipeline.query("x" * PIPELINE_WINDOW).query("NEVER").run()
        reader.join(timeout=10)
        assert isinstance(outcomes[0], IntegrityError)
        assert outcomes[1] is SKIPPED
        assert b"NEVER" not in drained[0]
        assert len(pipeline) == 0


def drain(server: socket.socket, at_least: int) -> bytes:
    """What the client wrote to `server`, at least `at_least` bytes of it."""
    got = b""
    while len(got) < at_least:
        chunk = server.recv(65536)
        if not chunk:
            break
        got += chunk
    server.settimeout(0.2)
    try:
        while chunk := server.recv(65536):
            got += chunk
    except TimeoutError:
        pass
    return got


def test_a_lost_connection_fails_the_run() -> None:
    """Verifies: [CLIENT Pipelines] run fails if the connection is lost (08006).

    What the requests answered before it is not given.
    """
    with Peer() as peer:
        conn = opened(peer)
        peer.reply(complete(), frame("G"))
        with pytest.raises(OperationalError) as lost:
            conn.pipeline().query("VALUES 1").query("VALUES 2").run()
        assert lost.value.sqlstate == "08006"
        assert conn.is_lost


def test_a_batch_that_cannot_be_undone_fails_the_run() -> None:
    """Verifies: [CLIENT Pipelines] run fails if a skipping batch cannot be undone.

    The failure of rolling back to the savepoint after the failed request.
    """
    with Peer() as peer:
        conn = opened(peer)
        peer.reply(
            error(-201, "23000", "duplicate", active=True),
            complete(active=True),
            complete(active=True),
            error(-917, "25000", "no such savepoint", active=True),
        )
        with pytest.raises(Exception, match="no such savepoint"):
            conn.pipeline().on_error(OnError.SKIP).query("INSERT 1").query(
                "INSERT 2"
            ).run()
