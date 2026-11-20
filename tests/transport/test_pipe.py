"""Tests of opening a Windows named pipe, its busy instances tried again."""

from __future__ import annotations

import sys

import pytest

from turborel import OperationalError
from turborel._transport.pipe import BUSY_RETRY, ERROR_PIPE_BUSY, open_pipe, retried


def busy() -> OSError:
    """Windows' error of a pipe whose every instance is busy."""
    error = OSError("busy")
    error.winerror = ERROR_PIPE_BUSY  # type: ignore[attr-defined]  # Windows' field.
    return error


def test_a_busy_pipe_is_tried_again_within_the_limit() -> None:
    """Verifies: [CLIENT Timeouts] a named pipe bounded only as it is opened.

    Busy, it is tried again every 10 milliseconds until it opens, or the
    connect timeout runs out; any other error at once. The clock here is
    the test's own.
    """
    tries: list[int] = []

    def opening() -> int:
        tries.append(1)
        if len(tries) < 3:
            raise busy()
        return len(tries)

    waits: list[float] = []
    assert retried(opening, 60.0, clock=lambda: 0.0, wait=waits.append) == 3
    assert waits == [BUSY_RETRY, BUSY_RETRY]
    times = iter([0.0, 1.0])

    def always_busy() -> int:
        raise busy()

    with pytest.raises(TimeoutError):
        retried(always_busy, 0.5, clock=lambda: next(times), wait=lambda _: None)

    def gone() -> int:
        raise FileNotFoundError

    with pytest.raises(FileNotFoundError):
        retried(gone, None, wait=lambda _: None)


@pytest.mark.skipif(sys.platform == "win32", reason="Windows has named pipes")
def test_a_named_pipe_is_refused_where_there_are_none() -> None:
    """Verifies: [DESIGN] D8 code of one platform refused elsewhere, saying so."""
    with pytest.raises(OperationalError) as failure:
        open_pipe(r"\\.\pipe\turborel", 1.0)
    assert "only Windows" in failure.value.message


@pytest.mark.skipif(sys.platform != "win32", reason="only Windows has named pipes")
def test_a_named_pipe_is_opened_and_read() -> None:
    """Verifies: [CLIENT Connecting] on Windows, connect over a named pipe.

    [PROTOCOL The Native Protocol] a named pipe where the operator asks:
    opened for identification, then read and written as a stream. The
    server's end is the standard library's own pipe listener.
    """
    import threading  # noqa: PLC0415  # Windows alone.
    from multiprocessing.connection import Listener  # noqa: PLC0415

    name = r"\\.\pipe\turborel-py-test"
    with Listener(name, family="AF_PIPE") as listener:
        accepted: list[object] = []

        def serve() -> None:
            server = listener.accept()
            server.send_bytes(b"ready")
            accepted.append(server)

        thread = threading.Thread(target=serve)
        thread.start()
        pipe = open_pipe(name, 5.0)
        thread.join(timeout=10)
        assert pipe.read(4) == (5).to_bytes(4, "big")
        assert pipe.read(5) == b"ready"
        pipe.close()
        for server in accepted:
            getattr(server, "close")()  # noqa: B009  # A Connection.
