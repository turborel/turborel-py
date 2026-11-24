"""Live tests of the routine debugger: two connections, one debugging the other."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import pytest

from turborel import Error, OperationalError, ProgrammingError
from turborel.client import (
    Action,
    Complete,
    EventKind,
    RoutineKind,
    Rowset,
    Trust,
    connect,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from live import Live

    from turborel.client import Connection, Event, Frame

PROCEDURE = """CREATE PROCEDURE DRAISE(IN PCT INTEGER) MODIFIES SQL DATA
BEGIN
  DECLARE N INTEGER DEFAULT 0;
  UPDATE DSTAFF SET SALARY = SALARY * (100 + PCT) / 100;
  SET N = (SELECT COUNT(*) FROM DSTAFF);
END"""
"""A procedure whose line 4 is its UPDATE, line 5 its SET."""


@pytest.fixture
def pair(live: Live) -> Iterator[tuple[Connection, Connection]]:
    """A target and its debugger, both ANN's, the procedure defined once."""
    target = connect((live.host, live.port), "ANN", Trust())
    debugger = connect((live.host, live.port), "ANN", Trust())
    defined = target.query(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.ROUTINES WHERE ROUTINE_NAME = 'DRAISE'"
    )
    assert isinstance(defined, Rowset)
    if defined.rows == [(0,)]:
        target.query("CREATE TABLE DSTAFF (ID INTEGER PRIMARY KEY, SALARY INTEGER)")
        target.query("INSERT INTO DSTAFF VALUES (1, 50000), (2, 60000)")
        target.query(PROCEDURE)
    target.query("COMMIT")
    yield target, debugger
    for conn in (debugger, target):
        if not conn.is_lost:
            conn.terminate()


def paused(event: Event | None) -> tuple[int | None, Frame]:
    """The breakpoint an Event paused at, if any, and its innermost frame."""
    assert event is not None
    assert event.kind is EventKind.PAUSED
    assert event.pause is not None
    return event.pause.breakpoint, event.pause.frames[-1]


def test_a_debugger_pauses_steps_and_resumes_its_target(
    pair: tuple[Connection, Connection],
) -> None:
    """Verifies: [CLIENT Debugging routines] attach, break, wait, frames, step, resume.

    [PROTOCOL Debug 'V'] the target's ID, the debugger attached to it, a
    breakpoint set at a line; [PROTOCOL Event 'W'] the target's CALL
    paused there, its frame's routine, line, parameters and variables
    told; Stack the same; a step over to the next line; continue to the
    CALL's end; detach. [PROTOCOL Capabilities] `debugger` asked for.
    """
    target, debugger = pair
    assert "debugger" in target.granted
    debugger.debug_attach(target.debug_id())
    point = debugger.debug_break("DRAISE", 4, kind=RoutineKind.PROCEDURE)
    assert (point.schema, point.line, point.condition) == ("ANN", 4, None)
    assert debugger.debug_breakpoints() == (point,)
    assert debugger.debug_stack() is None
    called: list[object] = []
    running = threading.Thread(
        target=lambda: called.append(target.query("CALL DRAISE(10)"))
    )
    running.start()
    try:
        number, frame = paused(debugger.debug_wait(10.0))
        assert number == point.number
        assert frame.origin is not None
        assert (frame.origin.kind, frame.origin.name) == (
            RoutineKind.PROCEDURE,
            "DRAISE",
        )
        assert (frame.visible, frame.line, frame.column) == (True, 4, 3)
        assert [(n.name, n.data_type, n.value) for n in frame.parameters] == [
            ("PCT", "INTEGER", 10)
        ]
        assert [(n.name, n.value) for n in frame.variables] == [("N", 0)]
        stacked = debugger.debug_stack()
        assert stacked is not None
        assert stacked.frames[-1] == frame
        debugger.debug_resume(Action.OVER)
        number, frame = paused(debugger.debug_wait(10.0))
        assert (number, frame.line) == (None, 5)
        debugger.debug_clear(point.number)
        debugger.debug_resume(Action.CONTINUE)
    finally:
        running.join(10.0)
    assert [type(c) for c in called] == [Complete]
    debugger.debug_detach()
    target.query("ROLLBACK")


def test_what_a_debugger_is_refused(
    live: Live, pair: tuple[Connection, Connection]
) -> None:
    """Verifies: [PROTOCOL Debug 'V'] the refusals, each keeping the session.

    08003 of an ID no connection served has; TBD01, SQLCODE -910, of a
    request but Identify and Attach of a connection attached to none, or
    a second Attach; 42000, SQLCODE -104, of a breakpoint in a routine its
    user neither owns nor holds DEBUG on.
    """
    target, debugger = pair
    with pytest.raises(OperationalError) as none:
        debugger.debug_attach(1 << 60)
    assert none.value.sqlstate == "08003"
    with pytest.raises(Error) as unattached:
        debugger.debug_resume()
    assert (unattached.value.sqlcode, unattached.value.sqlstate) == (-910, "TBD01")
    debugger.debug_attach(target.debug_id())
    with pytest.raises(ProgrammingError) as nowhere:
        debugger.debug_break("NO_SUCH_ROUTINE", 1)
    assert (nowhere.value.sqlcode, nowhere.value.sqlstate) == (-103, "42000")
    with pytest.raises(Error) as again:
        debugger.debug_attach(target.debug_id())
    assert again.value.sqlstate == "TBD01"
    debugger.debug_detach()
    assert not debugger.is_lost
    users = target.query(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.USERS WHERE USER_NAME = 'DBOB'"
    )
    assert isinstance(users, Rowset)
    target.query("ROLLBACK")
    if users.rows == [(0,)]:
        target.query("CREATE USER DBOB PASSWORD 'not used'")
    bob, bobs = (connect((live.host, live.port), "DBOB", Trust()) for _ in range(2))
    try:
        bob.debug_attach(bobs.debug_id())
        with pytest.raises(ProgrammingError) as foreign:
            bob.debug_break("DRAISE", 4, schema="ANN")
        assert (foreign.value.sqlcode, foreign.value.sqlstate) == (-104, "42000")
        bob.debug_detach()
    finally:
        bob.terminate()
        bobs.terminate()
