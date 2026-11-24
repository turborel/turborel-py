"""What each debugger's sample means: the requests encoded, the replies decoded.

[PROTOCOL Debug 'V'] [PROTOCOL Debugged 'V'] [PROTOCOL Event 'W'], each
written from its sample's meaning, by the sample's name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from turborel._codec import debug
from turborel._codec.debug import (
    Action,
    Breakpoint,
    CursorShown,
    Debugged,
    Event,
    EventKind,
    Frame,
    Named,
    Origin,
    Pause,
    RoutineKind,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from turborel._codec.replies import Reply

RAISE_PAY: Final = Breakpoint(1, "ANN", "RAISE_PAY", 4)
PAUSE: Final = Pause(
    1,
    (
        Frame(
            Origin(RoutineKind.PROCEDURE, "ANN", "RAISE_PAY", "ANN", "RAISE_PAY"),
            visible=True,
            place=1,
            line=4,
            column=3,
            parameters=(Named("PCT", "INTEGER", 10),),
            variables=(Named("N", "INTEGER", None),),
            cursors=(CursorShown("C", open=False, query="SELECT ID FROM STAFF"),),
        ),
    ),
)
"""The pause of `debugged-stack` and `event-paused`."""

REQUESTS: Final[dict[str, Callable[[], bytes]]] = {
    "debug-identify": lambda: debug.identify().encode(),
    "debug-attach": lambda: debug.attach(2).encode(),
    "debug-detach": lambda: debug.detach().encode(),
    "debug-break": lambda: debug.set_break(
        (RoutineKind.PROCEDURE, "ANN", "RAISE_PAY"), 4, "PCT > 5"
    ).encode(),
    "debug-clear": lambda: debug.clear(1).encode(),
    "debug-breakpoints": lambda: debug.breakpoints().encode(),
    "debug-resume": lambda: debug.resume(Action.OVER).encode(),
    "debug-interrupt": lambda: debug.interrupt().encode(),
    "debug-stack": lambda: debug.stack().encode(),
}
"""Each Debug request's sample."""

REPLIES: Final[dict[str, Reply]] = {
    "debugged-connection": Debugged(connection=2),
    "debugged-breakpoint": Debugged(breakpoint=RAISE_PAY),
    "debugged-breakpoints": Debugged(breakpoints=(RAISE_PAY,)),
    "debugged-running": Debugged(stacked=True),
    "debugged-stack": Debugged(stacked=True, pause=PAUSE),
    "event-paused": Event(EventKind.PAUSED, PAUSE),
    "event-timed-out": Event(EventKind.TIMED_OUT),
    "event-cancelled": Event(EventKind.CANCELLED),
    "event-ended": Event(EventKind.ENDED),
}
"""Each Debugged's and Event's sample."""
