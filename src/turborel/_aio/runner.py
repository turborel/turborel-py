"""A request's steps run over an asyncio stream, as `_session/runner.py` runs them.

The same generators of requests serve both: each `Send` written, each
`RECEIVE` awaited, a generator's own error raised, and an I/O error
losing the connection.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from turborel._errors import Error
from turborel._session.ops import Send

if TYPE_CHECKING:
    from turborel._aio.streams import AsyncStream
    from turborel._session.ops import Frame, Steps
    from turborel._session.state import Session

_T = TypeVar("_T")


async def run(stream: AsyncStream, session: Session, steps: Steps[_T]) -> _T:
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
                await stream.write(session.outgoing(step.data))
                sent = None
            else:
                sent = await stream.read_frame(session.max_body)
        except Error as e:
            steps.close()
            stream.close()
            session.lose(e)
            raise
