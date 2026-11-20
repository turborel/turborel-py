"""Large objects by their locators, as steps without I/O [PROTOCOL Lob 'L'].

A large object longer than the server's SERVER.LOB_INLINE_BYTES comes by
its locator, valid until its transaction ends, or a held one until it is
freed or a rollback ends it; its octets are read a range at a time. A
new one is created empty and appended to, then sent as a parameter by
its locator [CLIENT Large objects].
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from turborel._codec import requests
from turborel._codec.replies import Complete, Error, LobCreated, LobData
from turborel._errors import data_error
from turborel._session.ops import Send, receive

if TYPE_CHECKING:
    from turborel._session.ops import Steps
    from turborel._session.state import Session

CHUNK_OCTETS: Final = 262_144
"""The octets a read asks for at most, and a writer appends at once: 256 KiB."""

LOB_INLINE_OCTETS: Final = 64 * 1024
"""The longest value sent whole for a large object parameter, as the
server sends one whole by default; a longer one an import sends by a
locator."""

_LEAD_MASK: Final = 0xC0
_CONTINUATION: Final = 0x80
"""A UTF-8 continuation octet's top bits, under `_LEAD_MASK`."""

DATA_EXCEPTION: Final = "22000"
"""SQLSTATE 22000: a data exception, here a large object used wrongly."""


def _reply(session: Session) -> Steps[LobData | LobCreated]:
    reply = yield from receive(session)
    if isinstance(reply, LobData | LobCreated):
        return reply
    if isinstance(reply, Error):
        raise session.failed(reply.failure)
    raise session.lose_by("the server sent no Lob reply")


def _completed(session: Session) -> Steps[Complete]:
    reply = yield from receive(session)
    if isinstance(reply, Complete):
        return reply
    if isinstance(reply, Error):
        raise session.failed(reply.failure)
    raise session.lose_by("the server sent no completion")


def read(
    session: Session, locator: int, span: tuple[int, int], *, characters: bool
) -> Steps[bytes]:
    """At most `span`'s count of octets, or of characters, from its start."""
    start, count = span
    yield Send(requests.LobRead(locator, start, count, characters).encode())
    reply = yield from _reply(session)
    if isinstance(reply, LobCreated):
        raise session.lose_by("the server sent a locator for a Read")
    return reply.data


def create(session: Session, *, binary: bool) -> Steps[int]:
    """A new, empty large object's locator."""
    yield Send(requests.LobCreate(binary).encode())
    reply = yield from _reply(session)
    if isinstance(reply, LobData):
        raise session.lose_by("the server sent data for a Create")
    return reply.locator


def append(session: Session, locator: int, data: bytes) -> Steps[Complete]:
    """`data` added to the large object of `locator`."""
    yield Send(requests.LobAppend(locator, data).encode())
    return (yield from _completed(session))


def free(session: Session, locator: int) -> Steps[Complete]:
    """The locator ended, and the value it named."""
    yield Send(requests.LobFree(locator).encode())
    return (yield from _completed(session))


def hold(session: Session, locator: int) -> Steps[Complete]:
    """The locator kept valid past its transaction's commit."""
    yield Send(requests.LobHold(locator).encode())
    return (yield from _completed(session))


def held_range(value: str | bytes, span: tuple[int, int], *, characters: bool) -> bytes:
    """The range `span` of a large object held whole, as octets.

    By characters if `characters` and it is a character one; else by
    octets of its UTF-8.
    """
    start, count = span
    if isinstance(value, str):
        if characters:
            return value[start : start + count].encode("utf-8")
        value = value.encode("utf-8")
    return value[start : start + count]


def no_locator(lob: object) -> Exception:
    """A large object sent whole, given where a locator is wanted (22000)."""
    msg = f"the large object was sent whole, a {type(lob).__name__}: it has no locator"
    return data_error(msg, DATA_EXCEPTION)


def lead_octets(data: bytes) -> int:
    """The characters `data` begins, each counted at its lead octet."""
    return sum(1 for b in data if b & _LEAD_MASK != _CONTINUATION)
