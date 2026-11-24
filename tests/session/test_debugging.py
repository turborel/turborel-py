"""Tests of the routine debugger over a scripted server: requests, replies, Events."""

from __future__ import annotations

import pytest
from tests.kit import Peer, complete, error, frame, notice, ready, rows, u32, u64

from turborel import OperationalError, ProgrammingError
from turborel._auth.mechanisms import Trust
from turborel._transport.timeouts import Timeouts
from turborel.client import (
    Action,
    Breakpoint,
    Complete,
    Connection,
    Event,
    EventKind,
    RoutineKind,
)

TIMED_OUT = frame("W", b"\x01")
ENDED = frame("W", b"\x03")


def text(s: str) -> bytes:
    """A string field."""
    return u32(len(s.encode())) + s.encode()


def granted(peer: Peer, *capabilities: str) -> Connection:
    """A connection over `peer`, bounding its waits, granted `capabilities`."""
    peer.reply(ready(capabilities=capabilities))
    conn = Connection.open_within(peer.client, "ANN", Trust(), Timeouts(5.0, 5.0))
    peer.received()
    return conn


def test_each_request_is_sent_and_its_reply_given() -> None:
    """Verifies: [CLIENT Debugging routines] each request, its reply given.

    [PROTOCOL Debug 'V'] identify, attach, break, breakpoints, stack,
    resume, interrupt, clear and detach, each as the page lays it out;
    [PROTOCOL Debugged 'V'] a connection's ID, a breakpoint, the
    breakpoints and a stack; the others answered by a Complete.
    """
    found = u32(1) + text("ANN") + text("P") + u32(4) + b"\x01" + text("X > 1")
    with Peer() as peer:
        conn = granted(peer, "debugger")
        peer.reply(
            frame("V", b"\x00" + u64(9)),
            complete(),
            frame("V", b"\x01" + found),
            frame("V", b"\x02" + u32(1) + found),
            frame("V", b"\x03\x00"),
            complete(),
            complete(),
            complete(),
            complete(),
        )
        assert conn.debug_id() == 9
        conn.debug_attach(9)
        point = conn.debug_break("P", 4, kind=RoutineKind.FUNCTION, condition="X > 1")
        assert point == Breakpoint(1, "ANN", "P", 4, "X > 1")
        assert conn.debug_breakpoints() == (point,)
        assert conn.debug_stack() is None
        conn.debug_resume(Action.OUT)
        conn.debug_interrupt()
        conn.debug_clear(1)
        conn.debug_detach()
        sent = [peer.received() for _ in range(9)]
        assert sent[1] == (ord("V"), b"\x01" + u64(9))
        assert sent[2] == (
            ord("V"),
            b"\x03\x01" + text("") + text("P") + u32(4) + b"\x01" + text("X > 1"),
        )
        assert [body[0] for _, body in sent] == [0, 1, 3, 5, 8, 6, 7, 4, 2]
        assert sent[5][1] == b"\x06\x02"


def test_an_event_is_kept_and_ends_no_request() -> None:
    """Verifies: [PROTOCOL Event 'W'] an Event read wherever a reply is read.

    Kept for `debug_wait`, never ending a request's replies: the query
    takes its own Complete; the Events then given in order, a kept one
    first, before any the server sends after.
    """
    with Peer() as peer:
        conn = granted(peer, "debugger")
        peer.reply(TIMED_OUT, complete("02000"))
        done = conn.query("DELETE FROM T")
        assert isinstance(done, Complete)
        assert done.sqlcode == 100
        peer.reply(ENDED)
        assert conn.debug_wait(1.0) == Event(EventKind.TIMED_OUT)
        assert conn.debug_wait(1.0) == Event(EventKind.ENDED)


def test_debug_wait_gives_none_when_nothing_comes_in_time() -> None:
    """Verifies: [CLIENT Debugging routines] a wait bounded by its timeout.

    None if nothing comes in time, nothing of a frame lost, the
    connection's own timeout put back; a Notice that comes instead taken,
    and None given; an Event that then comes given.
    """
    with Peer() as peer:
        conn = granted(peer)
        assert conn.debug_wait(0.05) is None
        assert conn.read_timeout == 5.0
        peer.reply(notice("01000", "a note"))
        assert conn.debug_wait(1.0) is None
        assert [n.sqlstate for n in conn.take_notices()] == ["01000"]
        peer.reply(frame("W", b"\x02"))
        assert conn.debug_wait() == Event(EventKind.CANCELLED)


def test_what_the_debugger_is_refused() -> None:
    """Verifies: [CLIENT Debugging routines] the server's refusals, the session kept.

    TBD01 of a request its state does not allow; `debugger` not granted,
    08006 before anything is sent; a timeout of a stream given to `open`,
    08006 with the connection kept; a reply where an Event was waited
    for, the connection lost.
    """
    with Peer() as peer:
        conn = granted(peer, "debugger")
        peer.reply(error(-910, "TBD01", "not attached"))
        with pytest.raises(OperationalError) as state:
            conn.debug_resume()
        assert (state.value.sqlcode, state.value.sqlstate) == (-910, "TBD01")
        peer.reply(error(-104, "42000", "no DEBUG"))
        with pytest.raises(ProgrammingError):
            conn.debug_break("P", 1)
        assert not conn.is_lost
        peer.reply(rows())
        with pytest.raises(OperationalError, match="answered no request"):
            conn.debug_wait(1.0)
        assert getattr(conn, "is_lost")  # noqa: B009  # Read again, after the wait.
    with Peer() as peer:
        peer.reply(ready())
        conn = Connection.open(peer.client, "ANN", Trust())
        with pytest.raises(OperationalError, match="debugger"):
            conn.debug_id()
        with pytest.raises(OperationalError, match="without limit"):
            conn.debug_wait(0.1)
        assert not conn.is_lost
