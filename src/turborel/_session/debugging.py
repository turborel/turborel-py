"""The routine debugger's requests, as generators, for both clients.

[PROTOCOL Debug 'V'] With `debugger` (an extension), a connection
attaches to the session of another, by that one's ID, sets breakpoints in
the routines its user may debug, and drives that session as it pauses.
Each request but Identify, Break, Breakpoints and Stack is answered by a
Complete; those by Debugged. What the debugger hears of its target, an
Event, comes unasked between requests, and is kept until it is waited
for [PROTOCOL Event 'W'].
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from turborel._codec.debug import Debug, Debugged
from turborel._codec.replies import Error
from turborel._session.capabilities import DEBUGGER
from turborel._session.ops import Send, receive
from turborel._statements.prepared import completion

if TYPE_CHECKING:
    from turborel._session.ops import Steps
    from turborel._session.state import Session


def debugged(session: Session, request: Debug) -> Steps[Debugged]:
    """The Debugged that answers `request`.

    Raises:
        OperationalError: SQLSTATE 08006, before anything is sent, if
            `debugger` was not granted; of another reply, the connection
            lost.
        Error: The server's refusal: 08003, 42000, TBD01 and the like.
    """
    session.needs(DEBUGGER)
    yield Send(request.encode())
    reply = yield from receive(session)
    if isinstance(reply, Debugged):
        return reply
    if isinstance(reply, Error):
        raise session.failed(reply.failure)
    raise session.lose_by("the server sent no Debugged reply")


def done(session: Session, request: Debug) -> Steps[None]:
    """`request` sent and its Complete read.

    Raises:
        OperationalError: SQLSTATE 08006, before anything is sent, if
            `debugger` was not granted.
        Error: The server's refusal.
    """
    session.needs(DEBUGGER)
    yield Send(request.encode())
    yield from completion(session)
