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
from turborel._codec.failures import Notice
from turborel._codec.replies import (
    Challenge,
    Complete,
    Error,
    Pong,
    Ready,
    Status,
    decode,
)
from turborel._errors import OperationalError
from turborel._session.capabilities import CHANGE_USER, PING, RESET

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

Frame = tuple[int, bytes]
"""A frame read: its kind and its body."""

_T = TypeVar("_T")

Steps = Generator[Op, Frame | None, _T]
"""A request: its steps, then what it gives."""


def receive(session: Session) -> Steps[Reply]:
    """The next reply of a statement, each Notice and Status before it taken."""
    while True:
        frame = yield RECEIVE
        if frame is None:
            raise session.lose_by("cannot receive: no frame was read")
        compression = session.told.compress is not None
        try:
            kind, body = unwrap(
                *frame, compression=compression, max_body=session.max_body
            )
            reply = decode(kind, body)
        except OperationalError as e:
            raise session.lose(e) from e
        if isinstance(reply, Notice):
            session.told.notice(reply)
        elif isinstance(reply, Status):
            session.told.settings[reply.name] = reply.value
        else:
            return session.noted(reply)


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
            # Renewed as by Reset, so no transaction is active (RULES.md D8).
            session.active = False
            return
        elif isinstance(reply, Error):
            raise session.failed(reply.failure)
        else:
            raise session.lose_by("the server sent no Ready")
