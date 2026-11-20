"""Pipelining, as steps without I/O [CLIENT Pipelines] [PROTOCOL Requests].

A pipeline queues requests, writes them at once, and reads one outcome
for each, in order, as the server answers each request alone and in
turn: a batch costs one round trip, not one a request. The requests are
written a window of at most 64 KiB at a time, and its replies read
before the next is written, so a window fits the buffers of the two
sockets between client and server, and neither side waits on the other.

Each request is independent, so by default a failure is that request's
outcome alone, and the rest run. With skip on error the batch stops at
its first failure, the requests before it kept: a savepoint is set
before each request but the first, within the transaction, and the
requests after a failed one are undone to the savepoint set after it,
or never sent if their window was not yet written. A skipping batch is
one transaction, which under autocommit, of a batch that began none, is
committed as the batch ends.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Final

from turborel._codec import requests
from turborel._errors import Error
from turborel._session.ops import Send
from turborel._statements.prepared import completion, execute_reply, execute_request
from turborel._statements.queries import query_reply

if TYPE_CHECKING:
    from collections.abc import Sequence

    from turborel._client.statements import Statements
    from turborel._session.ops import Steps
    from turborel._session.state import Session
    from turborel._statements.prepared import Statement
    from turborel._statements.queries import Outcome

PIPELINE_WINDOW: Final = 64 * 1024
"""The most bytes of requests written before their replies are read."""
SAVEPOINT: Final = "TURBOREL_PIPELINE"
"""What the savepoints of skip on error are named by, then each its place."""


class Skipped:
    """A request not run, or run and undone, after an earlier one failed under skip."""

    def __repr__(self) -> str:
        """SKIPPED."""
        return "SKIPPED"


SKIPPED: Final = Skipped()
"""The outcome of a request skipped."""


@dataclass(frozen=True, slots=True)
class Query:
    """A statement queued, run as `query` runs it."""

    sql: str


@dataclass(frozen=True, slots=True)
class Execute:
    """An execution queued, run as `execute` runs it: all of a query's rows."""

    statement: Statement
    values: tuple[object, ...]


@dataclass(frozen=True, slots=True)
class Close:
    """The closing of a statement's cursor 0, of a pool's reset."""

    number: int


@dataclass(frozen=True, slots=True)
class Deallocate:
    """The destruction of a statement, of a pool's reset."""

    number: int


@dataclass(frozen=True, slots=True)
class Savepoint:
    """The savepoint skip on error sets before the request of this place."""

    place: int


Queued = Query | Execute | Close | Deallocate | Savepoint


def savepoint(place: int) -> str:
    """The savepoint set before the request of `place`."""
    return f"{SAVEPOINT}_{place}"


def guarded(queued: Sequence[Queued]) -> list[Queued]:
    """`queued`, a savepoint of its own before each request but the first."""
    sent: list[Queued] = []
    for place, item in enumerate(queued):
        if place:
            sent.append(Savepoint(place))
        sent.append(item)
    return sent


def encoded(session: Session, item: Queued, *, ends: bool) -> bytes:
    """The request `item` sends, ending the transaction with it if `ends`."""
    attributes = session.told.query_attributes()
    if isinstance(item, Query):
        return requests.Query(item.sql, ends=ends, attributes=attributes).encode()
    if isinstance(item, Execute):
        return execute_request(session, item.statement, item.values, ends=ends)
    if isinstance(item, Close):
        return requests.Close(item.number).encode()
    if isinstance(item, Deallocate):
        return requests.Deallocate(item.number).encode()
    return requests.Query(f"SAVEPOINT {savepoint(item.place)}").encode()


def windows(
    session: Session, queued: Sequence[Queued], *, ends: bool
) -> list[list[tuple[Queued, bytes]]]:
    """The requests of `queued`, in windows of at most `PIPELINE_WINDOW` bytes.

    A request longer than a window is alone in its own.
    """
    found: list[list[tuple[Queued, bytes]]] = []
    filled = PIPELINE_WINDOW
    for item in queued:
        frame = encoded(session, item, ends=ends)
        filled += len(frame)
        if filled > PIPELINE_WINDOW:
            found.append([])
            filled = len(frame)
        found[-1].append((item, frame))
    return found


def _reply(session: Session, item: Queued) -> Steps[Outcome]:
    if isinstance(item, Query | Savepoint):
        return (yield from query_reply(session))
    if isinstance(item, Execute):
        return (yield from execute_reply(session, item.statement))
    return (yield from completion(session))


def _window(
    session: Session, window: list[tuple[Queued, bytes]]
) -> Steps[list[object]]:
    """Write `window` at once and read its outcomes."""
    yield Send(b"".join(frame for _, frame in window))
    outcomes: list[object] = []
    for item, _ in window:
        try:
            outcomes.append((yield from _reply(session, item)))
        except Error as e:
            if session.is_lost():
                raise
            outcomes.append(e)
    return outcomes


def run(
    session: Session, queued: Sequence[Queued], *, skip: bool
) -> Steps[list[object]]:
    """The requests written a window at a time, one outcome read for each, in order.

    Raises:
        Error: The connection's failure, once it is lost; under skip, the
            failure of undoing the requests after a failed one.
    """
    began = session.active
    sent = guarded(queued) if skip else list(queued)
    ends = session.autocommit and not skip
    outcomes: list[object] = []
    for window in windows(session, sent, ends=ends):
        if skip and any(isinstance(o, Error) for o in outcomes):
            outcomes.extend(SKIPPED for _ in window)
            continue
        outcomes.extend((yield from _window(session, window)))
    if skip:
        yield from _settle(session, sent, outcomes, began=began)
    return [
        o
        for item, o in zip(sent, outcomes, strict=True)
        if not isinstance(item, Savepoint)
    ]


def _settle(
    session: Session, sent: list[Queued], outcomes: list[object], *, began: bool
) -> Steps[None]:
    """End a skipping batch: those after the first failure undone, savepoints released.

    And, under autocommit of a batch that began no transaction, its work
    committed.
    """
    failed = next((i for i, o in enumerate(outcomes) if isinstance(o, Error)), None)
    statements: list[str] = []
    if failed is not None:
        after = failed + 1
        if after < len(sent):
            following = sent[after]
            if isinstance(following, Savepoint) and not isinstance(
                outcomes[after], Error | Skipped
            ):
                statements.append(f"ROLLBACK TO SAVEPOINT {savepoint(following.place)}")
        for i in range(after, len(outcomes)):
            outcomes[i] = SKIPPED
    if len(sent) > 1:
        first = sent[1]
        if isinstance(first, Savepoint) and not isinstance(
            outcomes[1], Error | Skipped
        ):
            statements.append(f"RELEASE SAVEPOINT {savepoint(first.place)}")
    if not began and session.autocommit:
        statements.append("COMMIT")
    for sql in statements:
        yield Send(requests.Query(sql).encode())
        yield from query_reply(session)


class OnError(Enum):
    """What a pipeline does after a request fails."""

    CONTINUE = "continue"
    """Every request runs; a failure is its request's outcome alone."""
    SKIP = "skip"
    """The batch stops at its first failure, the requests after it skipped."""


class Pipeline:
    """Requests queued on a connection, written at once by `run`."""

    def __init__(self, connection: Statements) -> None:
        """An empty pipeline on `connection`, continuing on error."""
        self._connection = connection
        self._queued: list[Queued] = []
        self._on_error = OnError.CONTINUE

    def __len__(self) -> int:
        """How many requests are queued."""
        return len(self._queued)

    def query(self, sql: str) -> Pipeline:
        """Queue `sql`, run as `query` runs it; this pipeline, so calls chain."""
        self._queued.append(Query(sql))
        return self

    def execute(self, statement: Statement, values: Sequence[object] = ()) -> Pipeline:
        """Queue an execution of `statement` with `values`, as `execute` runs it."""
        self._queued.append(Execute(statement, tuple(values)))
        return self

    def release(self, number: int) -> Pipeline:
        """Queue the closing of statement `number`'s cursor, then its destruction."""
        self._queued.extend((Close(number), Deallocate(number)))
        return self

    def on_error(self, on_error: OnError) -> Pipeline:
        """What the batch does after a request fails."""
        self._on_error = on_error
        return self

    def run(self) -> list[object]:
        """Write the requests, a window at a time, and read one outcome each, in order.

        Each outcome is a query's `Rowset`, another statement's
        `Complete`, the request's failure, or `SKIPPED`.

        Raises:
            Error: The connection's failure, once it is lost; under skip,
                the failure of undoing the requests after a failed one.
        """
        queued, self._queued = self._queued, []
        skip = self._on_error is OnError.SKIP
        return self._connection._run(run(self._connection._session, queued, skip=skip))  # noqa: SLF001
