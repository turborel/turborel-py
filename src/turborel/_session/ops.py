"""A session's requests, as generators of what they send and wait for.

Each request is a generator: it yields `Send` of the frames to write and
`RECEIVE` for the next frame, and is sent the frame read, so the same
code runs over a blocking stream (`runner.py`) and over asyncio. Notices
and Statuses are taken as they come [PROTOCOL Conversations]; a reply
that cannot be read loses the connection.
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, TypeVar

from turborel._codec import requests
from turborel._codec.compress import unwrap
from turborel._codec.debug import Event
from turborel._codec.failures import Notice
from turborel._codec.replies import (
    Challenge,
    Complete,
    Description,
    Error,
    Pong,
    Ready,
    Rows,
    Status,
    completed_head,
    decode,
    ends_request,
)
from turborel._errors import Error as DriverError
from turborel._errors import OperationalError, connection_failure
from turborel._session.capabilities import CHANGE_USER, PING, RESET
from turborel._session.raising import raised

if TYPE_CHECKING:
    from turborel._auth.mechanisms import Mechanism
    from turborel._codec.replies import Reply
    from turborel._session.capabilities import Offer
    from turborel._session.state import Session


@dataclass(frozen=True, slots=True)
class Send:
    """Frames to write, whole."""

    data: bytes


class _Receive:
    """The next frame to read."""

    def __repr__(self) -> str:
        return "RECEIVE"


RECEIVE: Final = _Receive()
"""The step that reads the next frame."""

Op = Send | _Receive
"""A step of a request."""

_CONNECTION_EXCEPTION: Final = "08"

Frame = tuple[int, bytes]
"""A frame read: its kind and its body."""

_T = TypeVar("_T")

Steps = Generator[Op, Frame | None, _T]
"""A request: its steps, then what it gives."""


def _frame(session: Session) -> Steps[Frame]:
    """The next frame, whole and inflated; else the connection is lost."""
    frame = yield RECEIVE
    if frame is None:
        raise session.lose_by("cannot receive: no frame was read")
    compression = session.told.compress is not None
    try:
        return unwrap(*frame, compression=compression, max_body=session.max_body)
    except OperationalError as e:
        raise session.lose(e) from e


def _took(session: Session, reply: Reply) -> Reply | None:
    """`reply`, unless a Notice, Status or Event, which is taken; its end noted.

    An Event is kept for the debugger to read, and ends no request
    [PROTOCOL Event 'W'].
    """
    if isinstance(reply, Notice):
        session.told.notice(reply)
        return None
    if isinstance(reply, Status):
        session.told.settings[reply.name] = reply.value
        return None
    if isinstance(reply, Event):
        session.told.events.append(reply)
        return None
    return session.noted(reply)


def next_event(session: Session) -> Steps[Event | None]:
    """The next frame, read between requests where an Event is waited for.

    An Event given; a Notice or a Status taken, and None given.

    Raises:
        Error: Of an Error, the server's failure; of any other reply, a
            connection failure, as it answers no request.
    """
    kind, body = yield from _frame(session)
    reply = _decoded(session, kind, body)
    if isinstance(reply, Event):
        return reply
    if isinstance(reply, Error):
        raise session.failed(reply.failure)
    if _took(session, reply) is None:
        return None
    raise session.lose_by("the server answered no request")


def _decoded(session: Session, kind: int, body: bytes) -> Reply:
    """The reply of a frame read whole.

    Raises:
        Error: Of a malformed frame, SQLSTATE 08006, the connection lost;
            of a value the client cannot take, that value's failure, the
            connection kept, a Complete's head noted as its whole would be.
    """
    try:
        return decode(kind, body)
    except DriverError as e:
        if e.sqlstate.startswith(_CONNECTION_EXCEPTION):
            raise session.lose(e) from e
        head = completed_head(kind, body)
        if head is not None:
            session.noted(head)
        raise


def receive(session: Session, *, one: bool = False) -> Steps[Reply]:
    """The next reply of a statement, each Notice and Status before it taken.

    A reply holding a value the client cannot take fails the request
    alone, once the rest of its replies are read past, to the one that
    ends them, unless the request is answered by `one` reply [PROTOCOL
    Values and fields] (RULES.md D8).
    """
    while True:
        kind, body = yield from _frame(session)
        try:
            reply = _decoded(session, kind, body)
        except DriverError:
            if not one:
                yield from _drained(session, kind, body)
            raise
        if session.tap is not None and isinstance(reply, Description | Rows):
            session.tap(kind, body)
        taken = _took(session, reply)
        if taken is not None:
            return taken


def _drained(session: Session, kind: int, body: bytes) -> Steps[None]:
    """Read past the rest of a request's replies, to the one that ends them."""
    while not ends_request(kind, body):
        kind, body = yield from _frame(session)
        try:
            _took(session, _decoded(session, kind, body))
        except DriverError:
            # Another value refused is read past as the first was; a
            # malformed frame has lost the connection.
            if session.is_lost():
                raise


def terminated(session: Session, frame: Frame) -> None:
    """Take a frame the server sent after Terminate, before it closed.

    A Notice, a Status, a Pong or a debugger's Event is read past; an
    Error, as of a commit that failed as the session ended, is raised;
    any other reply is out of turn [PROTOCOL Terminate 'X'].

    Raises:
        Error: The server's failure, or a connection failure.
    """
    compression = session.told.compress is not None
    kind, body = unwrap(*frame, compression=compression, max_body=session.max_body)
    reply = decode(kind, body)
    if isinstance(reply, Error):
        raise raised(reply.failure)
    if not isinstance(reply, Notice | Status | Pong | Event):
        msg = "the server answered Terminate"
        raise connection_failure(msg)


def login(
    session: Session, user: str, mechanism: Mechanism, offer: Offer
) -> Steps[None]:
    """Hello, each Challenge answered, until Ready [PROTOCOL Opening a connection].

    Raises:
        Error: The server's refusal, or the mechanism's; a reply out of turn
            loses the connection.
    """
    hello = requests.Hello(
        user, mechanism.name, mechanism.initial(), offer.capabilities, offer.attributes
    )
    yield Send(hello.encode())
    while True:
        reply = yield from receive(session)
        if isinstance(reply, Challenge):
            yield Send(requests.Answer(mechanism.answer(reply.data)).encode())
        elif isinstance(reply, Ready):
            mechanism.ready()
            session.ready(reply.authorization, reply.key, reply.server)
            session.grant(reply.capabilities, offer.compress_from)
            return
        elif isinstance(reply, Error):
            mechanism.refused()
            raise session.failed(reply.failure)
        else:
            raise session.lose_by("the server sent no Ready")


def ping(session: Session) -> Steps[None]:
    """Ping, answered by Pong [PROTOCOL Ping 'G'] [CLIENT Controlling the session]."""
    session.needs(PING)
    yield Send(requests.Ping().encode())
    reply = yield from receive(session)
    if isinstance(reply, Error):
        raise session.failed(reply.failure)
    if not isinstance(reply, Pong):
        raise session.lose_by("the server sent no Pong")


def reset(session: Session) -> Steps[None]:
    """The session put back as it was at login [PROTOCOL Reset 'W'].

    A Notice of 01T01 comes first if a transaction was active, then a
    Status of each setting, then a Complete [CLIENT Controlling the session].
    """
    session.needs(RESET)
    yield Send(requests.Reset().encode())
    reply = yield from receive(session)
    if isinstance(reply, Error):
        raise session.failed(reply.failure)
    if not isinstance(reply, Complete):
        raise session.lose_by("the server sent no Complete")


def change_user(session: Session, user: str, mechanism: Mechanism) -> Steps[None]:
    """The connection authenticated again, as `user` [PROTOCOL ChangeUser 'U'].

    Accepted, the session is renewed as Reset renews it, under the new
    user and cancel key; refused, the connection fails.
    """
    session.needs(CHANGE_USER)
    sent = requests.ChangeUser(user, mechanism.name, mechanism.initial())
    yield Send(sent.encode())
    while True:
        reply = yield from receive(session)
        if isinstance(reply, Challenge):
            yield Send(requests.Answer(mechanism.answer(reply.data)).encode())
        elif isinstance(reply, Ready):
            mechanism.ready()
            session.ready(reply.authorization, reply.key, reply.server)
            # Renewed as by Reset, so no transaction is active.
            session.active = False
            return
        elif isinstance(reply, Error):
            raise session.failed(reply.failure)
        else:
            raise session.lose_by("the server sent no Ready")
