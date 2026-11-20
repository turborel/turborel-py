"""Tests of a connection's life: compression, terminate, limits, loss."""

from __future__ import annotations

import socket
import threading
import zlib

import pytest
from tests.kit import Peer, complete, error, frame, notice, ready, rows, status, u32

from turborel import IntegrityError, OperationalError
from turborel._codec.requests import QUERY, TERMINATE
from turborel.client import (
    Connection,
    Offer,
    Password,
    Scram,
    Tcp,
    Timeouts,
    Trust,
    connect,
    connect_local,
    connect_to,
)


def opened(peer: Peer, *capabilities: str, offer: Offer | None = None) -> Connection:
    """A connection over `peer`, granted `capabilities`."""
    peer.reply(ready(capabilities=capabilities))
    conn = Connection.open(peer.client, "ANN", Trust(), offer)
    peer.received()
    return conn


def test_compressed_frames_once_granted() -> None:
    """Verifies: [PROTOCOL Opening a connection] compression begins after Ready.

    [PROTOCOL Compressed frames] replies inflated, requests past the
    client's threshold compressed.
    """
    with Peer() as peer:
        conn = opened(peer, "compression", offer=Offer(compress_from=16).compressed())
        body = u32(0) + u32(5) + b"00000" + b"\x00"
        held = bytes([ord("K")]) + u32(len(body)) + zlib.compress(body)
        peer.reply(frame("z", held))
        conn.query("SELECT " + "1, " * 100 + "1")
        kind, sent = peer.received()
        assert kind == ord("z")
        assert sent[0] == QUERY


def test_terminate_reads_to_the_close() -> None:
    """Verifies: [PROTOCOL Terminate 'X'] the session ended; a failing commit's Error.

    [CLIENT Connecting] the server closes; a Notice or Status before it is
    no failure; an Error of the commit is raised; any other reply fails;
    the connection is lost after.
    """
    with Peer() as peer:
        conn = opened(peer)
        peer.reply(status("SCHEMA", "ANN"))
        peer.close()
        conn.terminate()
        assert conn.is_lost
        with pytest.raises(OperationalError):
            conn.terminate()
    with Peer() as peer:
        conn = opened(peer)
        peer.reply(error(-913, "23000", "a deferred constraint is broken"))
        peer.close()
        with pytest.raises(IntegrityError):
            conn.terminate()
    with Peer() as peer:
        conn = opened(peer)
        peer.reply(rows((True,)))
        peer.close()
        with pytest.raises(OperationalError):
            conn.terminate()


def test_terminate_sends_terminate() -> None:
    """Verifies: [PROTOCOL Terminate 'X'] Terminate, a header alone."""
    with Peer() as peer:
        conn = opened(peer)
        peer.reply(notice("01000", "bye"))
        peer.close()
        conn.terminate()


def test_a_lost_connection_gives_its_failure_again() -> None:
    """Verifies: [PROTOCOL Frames] a body cut short fails the connection.

    Every call after gives the same failure; closing it is told too.
    """
    with Peer() as peer:
        conn = opened(peer)
        peer.reply(b"K\x10\x00\x00\x00\x00")
        peer.close()
        with pytest.raises(OperationalError) as first:
            conn.query("VALUES 1")
        with pytest.raises(OperationalError) as again:
            conn.query("VALUES 1")
        assert again.value is first.value
    with Peer() as peer:
        conn = opened(peer)
        conn.close()
        assert conn.is_lost


def test_a_stream_given_to_open_is_bounded_by_its_maker() -> None:
    """Verifies: [CLIENT Timeouts] the read timeout changed, of connections made here.

    One over a stream the program opened refuses it (08006); a reply past
    the body the program takes loses the connection.
    """
    with Peer() as peer:
        conn = opened(peer)
        with pytest.raises(OperationalError):
            conn.set_read_timeout(1.0)
        assert conn.read_timeout is None
        conn.set_max_body(4)
        peer.reply(complete())
        with pytest.raises(OperationalError):
            conn.query("VALUES 1")
        assert conn.is_lost


def test_secrets_are_refused_over_plain_tcp_before_connecting() -> None:
    """Verifies: [CLIENT Connecting] a password, or SCRAM, refused over plain TCP.

    SQLSTATE 28000, before any connection is made.
    """
    for mechanism in (Password("p"), Scram("p")):
        with pytest.raises(OperationalError) as failure:
            connect(("127.0.0.1", 9), "ANN", mechanism)
        assert failure.value.sqlstate == "28000"


def test_nothing_to_connect_to_fails_the_connection(tmp_path: object) -> None:
    """Verifies: [CLIENT Connecting] a server that cannot be reached: 08006."""
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    with pytest.raises(OperationalError) as failure:
        connect(("127.0.0.1", port), "ANN", Trust())
    assert failure.value.sqlstate == "08006"
    with pytest.raises(OperationalError):
        connect_local(f"{tmp_path}/no-socket", "ANN", Trust())


def test_a_server_that_never_answers_runs_out_the_connect_timeout() -> None:
    """Verifies: [CLIENT Timeouts] the connect timeout bounds each step of the login.

    A wait that runs out loses the connection (08006), saying the server
    did not answer in time.
    """
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        with pytest.raises(OperationalError) as failure:
            connect_to(Tcp("127.0.0.1", port), "ANN", Trust(), Timeouts(connect=0.2))
    assert "did not answer in time" in failure.value.message


def test_a_connection_made_here_knows_its_target_and_canceller() -> None:
    """Verifies: [CLIENT Connecting] connect over TCP; its target and its canceller.

    [CLIENT Timeouts] its read timeout set, then changed; the canceller
    sends Cancel with the key on a connection of its own and waits for
    the close [PROTOCOL Cancel 'Z'].
    """
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        served: list[bytes] = []

        def serve() -> None:
            login, _ = listener.accept()
            with login:
                login.recv(4096)
                login.sendall(ready(capabilities=("ping",)))
                cancel, _ = listener.accept()
                with cancel:
                    served.append(cancel.recv(4096))

        thread = threading.Thread(target=serve)
        thread.start()
        conn = connect_to(Tcp("127.0.0.1", port), "ANN", Trust(), Timeouts(read=9))
        assert (conn.target, conn.read_timeout) == (Tcp("127.0.0.1", port), 9)
        conn.set_read_timeout(None)
        canceller = conn.canceller()
        assert canceller is not None
        canceller.cancel(within=5)
        thread.join(timeout=10)
        conn.close()
    assert served == [frame("Z", bytes(range(16)))]


def test_terminate_writes_a_header_alone() -> None:
    """Verifies: [PROTOCOL Terminate 'X'] Terminate written, a header alone."""
    with Peer() as peer:
        conn = opened(peer)
        peer.close()
        conn.terminate()
        assert peer.received() == (TERMINATE, b"")
