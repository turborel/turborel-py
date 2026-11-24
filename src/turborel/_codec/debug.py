"""The routine debugger's messages, with the capability `debugger` (an extension).

[PROTOCOL Debug 'V'] [PROTOCOL Debugged 'V'] [PROTOCOL Event 'W'] What a
debugger's connection asks of the session it debugs, another
connection's; what the server answers, but a completion; and what it
tells the debugger unasked as that session pauses, only between the
debugger's requests.

    Debug 'V'       what u8: 0 identify; 1 attach, connection u64; 2 detach;
                    3 break, kind u8, schema, name, line u32, conditioned
                    flag, the condition if 1; 4 clear, number u32;
                    5 breakpoints; 6 resume, action u8; 7 interrupt; 8 stack
    Debugged 'V'    what u8: 0 connection, ID u64; 1 breakpoint; 2 its
                    breakpoints, count u32, then each; 3 stack, paused flag,
                    the pause if 1
    Event 'W'       what u8: 0 paused, a pause; 1 timed out; 2 cancelled;
                    3 ended
    pause           reason u8, 0 a breakpoint, its number u32, 1 a step;
                    frames, count u32, then each, the outermost first
    frame           has origin flag, then kind u8, specific schema and
                    name, schema and name; visible flag; has place flag,
                    the character u64; has line flag, line u32 and column
                    u32; parameters and variables, each a named; cursors,
                    each name, open flag, query
    named           name, data type as SQL writes it, value
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, Final

from turborel._codec.fields import Writer
from turborel._codec.frames import encode_header
from turborel._codec.values import read_value

if TYPE_CHECKING:
    from turborel._codec.fields import Reader

DEBUG: Final = ord("V")
"""The kind of a Debug request, and of a Debugged reply."""
EVENT: Final = ord("W")
"""The kind of an Event, sent unasked by the server."""


class RoutineKind(IntEnum):
    """What a breakpoint's or a frame's routine is."""

    PROCEDURE = 0
    FUNCTION = 1
    TRIGGER = 2


class Action(IntEnum):
    """How a paused target goes on."""

    INTO = 0
    """To its next statement, in whatever frame."""
    OVER = 1
    """To the next of this frame, or of one it returns to."""
    OUT = 2
    """To the next of the frame this one returns to."""
    CONTINUE = 3
    """To a breakpoint."""


class EventKind(IntEnum):
    """What an Event tells of the target."""

    PAUSED = 0
    TIMED_OUT = 1
    """Paused past DEBUGGER.PAUSE_TIMEOUT_MS, it went on by itself."""
    CANCELLED = 2
    """Its statement was cancelled while it was paused."""
    ENDED = 3
    """Its session ended, and the debugger is detached."""


@dataclass(frozen=True, slots=True)
class Breakpoint:
    """A breakpoint set: its number, its routine's specific name, line, condition."""

    number: int
    schema: str
    name: str
    line: int
    condition: str | None = None


@dataclass(frozen=True, slots=True)
class Origin:
    """A frame's routine or trigger: its kind, specific name and name."""

    kind: RoutineKind
    specific_schema: str
    specific_name: str
    schema: str
    name: str


@dataclass(frozen=True, slots=True)
class Named:
    """A frame's parameter or variable: its name, type as SQL writes it, value."""

    name: str
    data_type: str
    value: object


@dataclass(frozen=True, slots=True)
class CursorShown:
    """A frame's local cursor: its name, whether it is open, its query."""

    name: str
    open: bool
    query: str


@dataclass(frozen=True, slots=True)
class Frame:
    """A run of a routine's or a trigger's body, in the call stack."""

    origin: Origin | None
    """Its routine; None of a statement run directly."""
    visible: bool
    """Whether the debugger may see into it; one it may not shows its origin alone."""
    place: int | None
    """Where its statement begins, in characters from its routine's text's start."""
    line: int | None
    """That place's line, from 1."""
    column: int | None
    """That place's column, from 1."""
    parameters: tuple[Named, ...]
    """Its parameters, or a trigger's transition variables, in order."""
    variables: tuple[Named, ...]
    cursors: tuple[CursorShown, ...]


@dataclass(frozen=True, slots=True)
class Pause:
    """A target paused: at a breakpoint, its number, or a step's end; its frames."""

    breakpoint: int | None
    """The number of the breakpoint it paused at; None of a step's end."""
    frames: tuple[Frame, ...]
    """Its call stack, the outermost first, the paused statement's last."""


@dataclass(frozen=True, slots=True)
class Event:
    """What the debugger hears of its target, unasked [PROTOCOL Event 'W']."""

    kind: EventKind
    pause: Pause | None = None
    """Of PAUSED, the pause."""


@dataclass(frozen=True, slots=True)
class Debugged:
    """What a Debug request gave back [PROTOCOL Debugged 'V'], by what it asked."""

    connection: int | None = None
    """Identify's: the connection's ID."""
    breakpoint: Breakpoint | None = None
    """Break's: the breakpoint set."""
    breakpoints: tuple[Breakpoint, ...] | None = None
    """Breakpoints': each set, in order."""
    stacked: bool = False
    """Whether it answers Stack, of `pause`, None if the target runs."""
    pause: Pause | None = None


@dataclass(frozen=True, slots=True)
class Debug:
    """A Debug request [PROTOCOL Debug 'V']: what it asks, then its fields."""

    what: int
    fields: bytes = b""

    def encode(self) -> bytes:
        """Its frame."""
        body = bytes([self.what]) + self.fields
        return encode_header(DEBUG, len(body)) + body


def identify() -> Debug:
    """Identify: this connection's ID."""
    return Debug(0)


def attach(connection: int) -> Debug:
    """Attach to the session of the connection `connection`."""
    w = Writer()
    w.u64(connection)
    return Debug(1, w.data())


def detach() -> Debug:
    """Detach: the breakpoints gone, the target going on."""
    return Debug(2)


def set_break(
    routine: tuple[RoutineKind, str, str], line: int, condition: str | None
) -> Debug:
    """Break at `line` of the routine of kind, schema and name `routine`."""
    kind, schema, name = routine
    w = Writer()
    w.u8(kind)
    w.string(schema)
    w.string(name)
    w.u32(line)
    _given(w, condition)
    return Debug(3, w.data())


def clear(number: int) -> Debug:
    """Clear the breakpoint `number`."""
    w = Writer()
    w.u32(number)
    return Debug(4, w.data())


def breakpoints() -> Debug:
    """Breakpoints: each set, in order."""
    return Debug(5)


def resume(action: Action) -> Debug:
    """Resume the paused target as `action` says."""
    return Debug(6, bytes([action]))


def interrupt() -> Debug:
    """Interrupt the running target at its next statement."""
    return Debug(7)


def stack() -> Debug:
    """Stack: the target's pause, if it is paused."""
    return Debug(8)


def _given(w: Writer, text: str | None) -> None:
    w.flag(text is not None)
    if text is not None:
        w.string(text)


def _text_given(r: Reader) -> str | None:
    return r.string() if r.flag() else None


def _enum(r: Reader, kind: type[RoutineKind], what: str) -> RoutineKind:
    code = r.u8()
    if code not in _KINDS:
        msg = f"{code} is not {what}"
        raise r.malformed(msg)
    return kind(code)


def read_breakpoint(r: Reader) -> Breakpoint:
    """A breakpoint: number, routine, line, its condition if given."""
    return Breakpoint(r.u32(), r.string(), r.string(), r.u32(), _text_given(r))


def _named(r: Reader) -> Named:
    return Named(r.string(), r.string(), read_value(r))


def _cursor(r: Reader) -> CursorShown:
    return CursorShown(r.string(), r.flag(), r.string())


def _frame(r: Reader) -> Frame:
    origin = None
    if r.flag():
        kind = _enum(r, RoutineKind, "a kind of routine")
        origin = Origin(kind, r.string(), r.string(), r.string(), r.string())
    visible = r.flag()
    place = r.u64() if r.flag() else None
    line, column = (r.u32(), r.u32()) if r.flag() else (None, None)
    parameters, variables = tuple(r.items(_named)), tuple(r.items(_named))
    cursors = tuple(r.items(_cursor))
    return Frame(origin, visible, place, line, column, parameters, variables, cursors)


def read_pause(r: Reader) -> Pause:
    """A pause: at a breakpoint or a step's end, then its frames."""
    reason = r.u8()
    if reason not in (_AT_BREAKPOINT, _STEPPED):
        msg = f"no pause is for reason {reason}"
        raise r.malformed(msg)
    number = r.u32() if reason == _AT_BREAKPOINT else None
    return Pause(number, tuple(r.items(_frame)))


def read_debugged(r: Reader) -> Debugged:
    """A Debugged reply's body."""
    what = r.u8()
    if what == _CONNECTION:
        return Debugged(connection=r.u64())
    if what == _BREAKPOINT:
        return Debugged(breakpoint=read_breakpoint(r))
    if what == _LISTED:
        return Debugged(breakpoints=tuple(r.items(read_breakpoint)))
    if what == _STACKED:
        return Debugged(stacked=True, pause=read_pause(r) if r.flag() else None)
    msg = f"no Debugged reply is of kind {what}"
    raise r.malformed(msg)


def read_event(r: Reader) -> Event:
    """An Event's body."""
    what = r.u8()
    if what not in _EVENTS:
        msg = f"no debugger's event is of kind {what}"
        raise r.malformed(msg)
    kind = EventKind(what)
    return Event(kind, read_pause(r) if kind == EventKind.PAUSED else None)


_KINDS: Final = frozenset(int(k) for k in RoutineKind)
_EVENTS: Final = frozenset(int(k) for k in EventKind)
_AT_BREAKPOINT: Final = 0
_STEPPED: Final = 1
_CONNECTION: Final = 0
_BREAKPOINT: Final = 1
_LISTED: Final = 2
_STACKED: Final = 3
