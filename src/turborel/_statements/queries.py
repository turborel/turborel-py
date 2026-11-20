"""Direct statements: a query's rows, whole or a batch at a time, or several.

[PROTOCOL Query 'Q'] [CLIENT Running statements] [CLIENT Controlling the
session]. A query is answered by a Description, its Rows and a Complete;
another statement by a Complete; a failure by an Error. Under autocommit
the statement is its own transaction, ended with it by `ends`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from turborel._codec import requests
from turborel._codec.replies import Complete, Description, Error, Rows, Suspended
from turborel._errors import Error as DriverError
from turborel._session.capabilities import MULTI_STATEMENT
from turborel._session.ops import Send, receive

if TYPE_CHECKING:
    from turborel._codec.composites import Column
    from turborel._session.ops import Steps
    from turborel._session.state import Session


@dataclass(frozen=True, slots=True)
class Rowset:
    """A query's outcome: its columns and its rows."""

    columns: tuple[Column, ...]
    rows: list[tuple[object, ...]]


Outcome = Rowset | Complete
"""A statement's outcome: a query's rows, or another statement's completion."""


class Sink(Protocol):
    """What takes a query's rows a batch at a time, as they come."""

    def columns(self, columns: tuple[Column, ...]) -> None:
        """The query's columns, before its rows."""

    def rows(self, rows: tuple[tuple[object, ...], ...]) -> None:
        """A batch of its rows."""


@dataclass(slots=True)
class Ran:
    """The outcomes of several statements, and the failure that stopped the rest."""

    outcomes: list[Outcome] = field(default_factory=list)
    failure: DriverError | None = None


def _sent(session: Session, sql: str, *, multi: bool = False) -> Send:
    attributes = session.told.query_attributes()
    query = requests.Query(
        sql, ends=session.autocommit, attributes=attributes, multi=multi
    )
    return Send(query.encode())


def query(session: Session, sql: str) -> Steps[Outcome]:
    """One statement, its rows read whole."""
    yield _sent(session, sql)
    outcome, _ = yield from _outcome(session)
    return outcome


def _first(session: Session) -> Steps[Complete | Description]:
    """A statement's first reply: a Complete, or its rows' Description."""
    reply = yield from receive(session)
    if isinstance(reply, Complete | Description):
        return reply
    if isinstance(reply, Error):
        raise session.failed(reply.failure)
    raise session.lose_by("the server sent no result")


def query_reply(session: Session) -> Steps[Outcome]:
    """The reply to a Query of one statement sent: a query's rows, or its completion."""
    outcome, _ = yield from _outcome(session)
    return outcome


def _outcome(session: Session) -> Steps[tuple[Outcome, bool]]:
    """A statement's outcome, and whether another's replies follow (tag 5)."""
    first = yield from _first(session)
    if isinstance(first, Complete):
        return first, first.more
    found: list[tuple[object, ...]] = []
    while True:
        reply = yield from receive(session)
        if isinstance(reply, Rows):
            found.extend(reply.rows)
        elif isinstance(reply, Complete):
            return Rowset(first.columns, found), reply.more
        elif isinstance(reply, Error):
            raise session.failed(reply.failure)
        else:
            raise session.lose_by("the server broke off its rows")


def query_into(session: Session, sql: str, sink: Sink) -> Steps[int | Complete]:
    """One statement, its rows given to `sink` a batch at a time.

    Returns:
        The rows given, of a query; the completion of another statement.
    """
    yield _sent(session, sql)
    first = yield from _first(session)
    if isinstance(first, Complete):
        return first
    sink.columns(first.columns)
    count = 0
    while True:
        reply = yield from receive(session)
        if isinstance(reply, Rows):
            count += len(reply.rows)
            sink.rows(reply.rows)
        elif isinstance(reply, Complete):
            return count
        elif isinstance(reply, Error):
            raise session.failed(reply.failure)
        else:
            raise session.lose_by("the server broke off its rows")


def query_many(session: Session, sql: str) -> Steps[Ran]:
    """A text of several statements as one request, run until one fails.

    With `multi-statement`: each statement's outcome in order, and the
    failure that stopped the rest; a failure that loses the connection is
    raised instead.
    """
    session.needs(MULTI_STATEMENT)
    yield _sent(session, sql, multi=True)
    ran = Ran()
    while True:
        try:
            outcome, more = yield from _outcome(session)
        except DriverError as e:
            if session.is_lost():
                raise
            ran.failure = e
            return ran
        ran.outcomes.append(outcome)
        if not more:
            return ran


def rows(session: Session) -> Steps[tuple[list[tuple[object, ...]], bool]]:
    """Rows until a Complete, or Suspended: the rows, and whether more are left."""
    found: list[tuple[object, ...]] = []
    while True:
        reply = yield from receive(session)
        if isinstance(reply, Rows):
            found.extend(reply.rows)
        elif isinstance(reply, Complete | Suspended):
            return found, isinstance(reply, Suspended)
        elif isinstance(reply, Error):
            raise session.failed(reply.failure)
        else:
            raise session.lose_by("the server broke off its rows")
