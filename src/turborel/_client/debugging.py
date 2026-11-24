"""The routine debugger, from the blocking client (an extension).

[CLIENT Debugging routines] A connection granted `debugger` attaches to
the session of another connection, by that one's ID, sets breakpoints in
the routines and triggers its user may debug, and drives that session's
routines as they pause, step by step, reading their call stack,
parameters, variables and cursors. What it hears of its target, an
`Event`, comes unasked, and is kept until `debug_wait` reads it. The
target runs its statements as ever, on its own connection, often on
another thread.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from turborel._client.bulk import Bulk
from turborel._codec import debug
from turborel._codec.debug import Action, Breakpoint, Event, Pause, RoutineKind
from turborel._errors import Error, connection_failure
from turborel._session import debugging, ops

if TYPE_CHECKING:
    from turborel._codec.debug import Debugged


class Debugging(Bulk):
    """A connection's routine debugger, with `debugger`."""

    def _debugged(self, request: debug.Debug) -> Debugged:
        return self._run(debugging.debugged(self._session, request))

    def debug_id(self) -> int:
        """This connection's ID, which another attaches to its session by.

        As INFORMATION_SCHEMA.CONNECTIONS shows it.

        Raises:
            OperationalError: SQLSTATE 08006, if `debugger` was not granted.
        """
        told = self._debugged(debug.identify())
        if told.connection is None:
            raise self._session.lose_by("the server sent no connection's ID")
        return told.connection

    def debug_attach(self, connection: int) -> None:
        """This connection made the debugger of the session of `connection`.

        One of its own user's, or any if its user is the database's owner
        or holds the role MONITOR.

        Raises:
            Error: SQLSTATE 08003 if no connection of that ID is served
                whose session this one may debug; TBD01 if this one is
                attached already, or the session is this one's or has a
                debugger already.
        """
        self._run(debugging.done(self._session, debug.attach(connection)))

    def debug_detach(self) -> None:
        """This connection detached: its breakpoints gone, its target going on.

        Raises:
            Error: SQLSTATE TBD01 if it is attached to none.
        """
        self._session.told.events.clear()
        self._run(debugging.done(self._session, debug.detach()))

    def debug_break(
        self,
        name: str,
        line: int,
        *,
        schema: str = "",
        kind: RoutineKind = RoutineKind.PROCEDURE,
        condition: str | None = None,
    ) -> Breakpoint:
        """A breakpoint at `line`, from 1, of the routine or trigger `name`.

        `name` is a routine's specific name, or its name if it is the one
        routine of `kind` so named, or a trigger's name; `schema` empty is
        the session's default schema. The target pauses at each statement
        that begins on the line, where `condition`, a `<search condition>`
        over the frame's parameters and variables, is true, if given.

        Raises:
            Error: SQLCODE -103 of no such routine or line, -104 (42000)
                if the user holds no DEBUG on it; SQLSTATE TBD01 if this
                connection is attached to none.
        """
        told = self._debugged(debug.set_break((kind, schema, name), line, condition))
        if told.breakpoint is None:
            raise self._session.lose_by("the server sent no breakpoint")
        return told.breakpoint

    def debug_clear(self, number: int) -> None:
        """The breakpoint `number` cleared.

        Raises:
            Error: SQLSTATE TBD01 if there is none of that number, or this
                connection is attached to none.
        """
        self._run(debugging.done(self._session, debug.clear(number)))

    def debug_breakpoints(self) -> tuple[Breakpoint, ...]:
        """The breakpoints set, in the order they were set.

        Raises:
            Error: SQLSTATE TBD01 if this connection is attached to none.
        """
        told = self._debugged(debug.breakpoints())
        if told.breakpoints is None:
            raise self._session.lose_by("the server sent no breakpoints")
        return told.breakpoints

    def debug_resume(self, action: Action = Action.CONTINUE) -> None:
        """The paused target told to go on: into, over, out, or on to a breakpoint.

        Raises:
            Error: SQLSTATE TBD01 if the target is not paused, or this
                connection is attached to none.
        """
        self._run(debugging.done(self._session, debug.resume(action)))

    def debug_interrupt(self) -> None:
        """The running target told to pause at the next statement it may be seen in.

        Raises:
            Error: SQLSTATE TBD01 if this connection is attached to none.
        """
        self._run(debugging.done(self._session, debug.interrupt()))

    def debug_stack(self) -> Pause | None:
        """The target's pause, its frames the outermost first; None if it runs.

        Raises:
            Error: SQLSTATE TBD01 if this connection is attached to none.
        """
        told = self._debugged(debug.stack())
        if not told.stacked:
            raise self._session.lose_by("the server sent no stack")
        return told.pause

    def debug_wait(self, timeout: float | None = None) -> Event | None:
        """The next Event of the target not yet read; None if none came in time.

        One kept, else the next the server sends, waited for at most
        `timeout` seconds, without limit if None. It is read between
        requests, never while one is answered. A Notice or Status that
        comes instead is taken, and None given.

        Raises:
            OperationalError: SQLSTATE 08006 of a `timeout` given of a stream
                given to `open`, which waits only without limit, the
                connection kept; of a reply where an Event was waited for,
                or the server gone, the connection lost.
        """
        session = self._session
        if session.lost is not None:
            raise session.lost
        if session.told.events:
            return session.told.events.popleft()
        if timeout is not None and not self._bounded:
            msg = "a stream given to open waits for an event only without limit"
            raise connection_failure(msg)
        try:
            arrived = self._stream.arrives_within(timeout, self._read_timeout)
        except Error as e:
            self._stream.close()
            raise session.lose(e) from e
        if not arrived:
            return None
        return self._run(ops.next_event(session))
