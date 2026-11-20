"""Prepared statements and their cursors [CLIENT Prepared statements].

A statement is prepared once under the client's own number, then
executed with values for its `?` marks as many times as wanted [PROTOCOL
Prepare 'P'] [PROTOCOL Execute 'E']. A query's cursor gives its rows a
batch at a time, Suspended saying more are left [PROTOCOL Fetch 'F'], and
is closed [PROTOCOL Close 'C']; with `cursors`, several cursors of one
statement are open at once, each by a number of the program's; with
`describe`, a statement or an open cursor is described again [PROTOCOL
Describe 'Y'].
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from turborel._codec import requests
from turborel._codec.replies import Complete, Description, Error, Prepared
from turborel._session.capabilities import CURSORS, DESCRIBE, FETCH_ENDS
from turborel._session.ops import Send, receive
from turborel._statements.queries import Rowset, rows

if TYPE_CHECKING:
    from collections.abc import Sequence

    from turborel._codec.composites import Column, Parameter
    from turborel._session.ops import Steps
    from turborel._session.state import Session
    from turborel._statements.queries import Outcome

_U32_SPAN = 1 << 32


@dataclass(frozen=True, slots=True)
class Statement:
    """A prepared statement: its number, the type each `?` takes, its columns."""

    number: int
    parameters: tuple[Parameter, ...]
    """In the order of their `?` marks."""
    columns: tuple[Column, ...]
    """A query's columns; none of another statement."""


@dataclass(frozen=True, slots=True)
class Batch:
    """A cursor's rows sent at once, and whether it has more."""

    rows: list[tuple[object, ...]]
    more: bool


def completion(session: Session) -> Steps[Complete]:
    """A request's Complete, or its Error raised."""
    reply = yield from receive(session)
    if isinstance(reply, Complete):
        return reply
    if isinstance(reply, Error):
        raise session.failed(reply.failure)
    raise session.lose_by("the server sent no completion")


def _prepared(session: Session) -> Steps[Statement]:
    reply = yield from receive(session)
    if isinstance(reply, Prepared):
        return Statement(reply.statement, reply.parameters, reply.columns)
    if isinstance(reply, Error):
        raise session.failed(reply.failure)
    raise session.lose_by("the server sent no Prepared")


def prepare(session: Session, sql: str) -> Steps[Statement]:
    """`sql` prepared under the session's next number."""
    number = session.next_statement
    session.next_statement = (number + 1) % _U32_SPAN
    yield Send(requests.Prepare(number, sql).encode())
    return (yield from _prepared(session))


def _execute(
    session: Session,
    cursor: tuple[Statement, int, bool],
    values: Sequence[object],
    rows_now: int,
) -> Send:
    """An Execute of the statement's cursor, ending the transaction if `ends`."""
    statement, number, ends = cursor
    sent = requests.Execute(
        statement.number,
        values,
        rows=rows_now,
        ends=ends,
        attributes=session.told.query_attributes(),
        cursor=number,
    )
    return Send(sent.encode())


def execute(
    session: Session, statement: Statement, values: Sequence[object]
) -> Steps[Outcome]:
    """The statement executed with `values`: a query's rows whole, or its completion."""
    yield _execute(session, (statement, 0, session.autocommit), values, 0)
    if not statement.columns:
        return (yield from completion(session))
    found, _ = yield from rows(session)
    return Rowset(statement.columns, found)


def open_cursor(
    session: Session,
    cursor: tuple[Statement, int],
    values: Sequence[object],
    rows_now: int,
) -> Steps[Batch]:
    """A query's cursor opened, its first `rows_now` rows (0 for all)."""
    statement, number = cursor
    session.needs(CURSORS, ok=number == 0)
    # Under autocommit a cursor ends its transaction as it ends, with
    # `fetch-ends`; without, the transaction is left to the program.
    ends = session.autocommit and FETCH_ENDS in session.told.granted
    yield _execute(session, (statement, number, ends), values, rows_now)
    found, more = yield from rows(session)
    return Batch(found, more)


def fetch(
    session: Session, cursor: tuple[Statement, int], rows_now: int
) -> Steps[Batch]:
    """At most `rows_now` more rows of an open cursor (0 for all)."""
    statement, number = cursor
    session.needs(CURSORS, ok=number == 0)
    yield Send(requests.Fetch(statement.number, rows=rows_now, cursor=number).encode())
    found, more = yield from rows(session)
    return Batch(found, more)


def close(session: Session, cursor: tuple[Statement, int]) -> Steps[None]:
    """An open cursor closed."""
    statement, number = cursor
    session.needs(CURSORS, ok=number == 0)
    yield Send(requests.Close(statement.number, cursor=number).encode())
    yield from completion(session)


def describe(session: Session, statement: Statement) -> Steps[Statement]:
    """A prepared statement described again: its parameters and columns."""
    session.needs(DESCRIBE)
    yield Send(requests.Describe(statement.number).encode())
    return (yield from _prepared(session))


def describe_cursor(
    session: Session, cursor: tuple[Statement, int]
) -> Steps[tuple[Column, ...]]:
    """An open cursor's columns."""
    statement, number = cursor
    session.needs(DESCRIBE)
    yield Send(requests.Describe(statement.number, cursor=number).encode())
    reply = yield from receive(session)
    if isinstance(reply, Description):
        return reply.columns
    if isinstance(reply, Error):
        raise session.failed(reply.failure)
    raise session.lose_by("the server sent no Description")


def deallocate(session: Session, statement: Statement) -> Steps[None]:
    """A prepared statement destroyed."""
    yield Send(requests.Deallocate(statement.number).encode())
    yield from completion(session)
