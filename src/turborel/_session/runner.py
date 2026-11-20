"""A request's steps run over a blocking stream.

Each `Send` is written, each `RECEIVE` read, the frame's body bounded by
the session's longest body taken. An I/O failure loses the connection:
the request is given up and the stream closed, and the failure is given
to every call after it, as turborel-client's connection does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from turborel._errors import Error
from turborel._session.ops import Send

if TYPE_CHECKING:
    from turborel._session.ops import Frame, Steps
    from turborel._session.state import Session
    from turborel._transport.stream import Stream

_T = TypeVar("_T")


def run(stream: Stream, session: Session, steps: Steps[_T]) -> _T:
    """What `steps` gives, run over `stream`.

    Raises:
        Error: The connection's failure, if it was lost before; the
            request's own; or an I/O failure, which loses the connection.
    """
    if session.lost is not None:
        steps.close()
        raise session.lost
    sent: Frame | None = None
    while True:
        try:
            step = steps.send(sent)
        except StopIteration as stop:
            result: _T = stop.value
            return result
        except Error:
            if session.is_lost():
                stream.close()
            raise
        try:
            if isinstance(step, Send):
                stream.write(session.outgoing(step.data))
                sent = None
            else:
                sent = stream.read_frame(session.max_body)
        except Error as e:
            steps.close()
            stream.close()
            session.lose(e)
            raise
