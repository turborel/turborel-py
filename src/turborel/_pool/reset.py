"""A pooled connection's check and reset [CLIENT Pools].

Granted `ping`, a connection is checked by Ping, which the server
answers with no statement; granted `reset`, it is reset by Reset, which
ends all the session holds in one request, its transaction, prepared
statements, cursors, temporary tables and settings, and keeps its user;
then the program's own statements run.

A server that grants neither is checked by ROLLBACK, which a session
outside a transaction completes doing nothing, and reset in one
pipeline: its transaction rolled back, the statements it prepared closed
and destroyed, its user, schema and zone those of its login, then the
program's own statements. A setting a borrower SET stays, as no
statement sets every setting back. Either way autocommit is off after.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, TypeVar

from turborel._errors import Error, connection_failure
from turborel._pipeline.pipelines import Pipeline
from turborel._session.capabilities import PING, RESET
from turborel._transport.timeouts import CONNECT_WITHIN

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from turborel._client.connection import Connection

RESET_WITHIN: Final = CONNECT_WITHIN
"""How long a pooled connection's check and reset wait on its server, at most."""
RESET_MOST_STATEMENTS: Final = 256
"""The most statements a borrower may leave prepared for the connection to be reset."""
CHECK: Final = "ROLLBACK"
"""What a connection is checked by, of a server that grants no `ping`."""

_T = TypeVar("_T")


def _bounded(connection: Connection, step: Callable[[Connection], _T]) -> _T:
    """`step` of `connection`, each wait at most `RESET_WITHIN`, its limit put back."""
    before = connection.read_timeout
    within = RESET_WITHIN if before is None else min(before, RESET_WITHIN)
    connection.set_read_timeout(within)
    try:
        return step(connection)
    finally:
        if not connection.is_lost:
            connection.set_read_timeout(before)


def answers(connection: Connection) -> None:
    """Check that `connection` answers.

    Raises:
        Error: A connection failure, if it is lost or does not answer.
    """
    if PING in connection.granted:
        _bounded(connection, lambda c: c.ping())
    else:
        _bounded(connection, lambda c: c.query(CHECK))


def _delimited(name: str) -> str:
    """`name` as a literal of a delimited identifier, as SET SCHEMA takes one."""
    body = name.replace('"', '""').replace("'", "''")
    return f"'\"{body}\"'"


def reset(connection: Connection, more: Sequence[str]) -> None:
    """Give `connection`'s session back as it logged in, then run `more`.

    Raises:
        Error: A connection failure; any statement's failure but those
            destroying statements already gone; too many statements left
            prepared.
    """
    _bounded(connection, lambda c: _reset_now(c, more))


def _reset_now(connection: Connection, more: Sequence[str]) -> None:
    session = connection._session  # noqa: SLF001  # The pool's own.
    if connection.is_lost:
        msg = "a lost connection is not given back"
        raise connection_failure(msg)
    if RESET in connection.granted:
        connection.autocommit = False
        connection.reset()
        # Every statement it prepared went with the session it had.
        session.next_statement = 0
        for sql in more:
            connection.query(sql)
        return
    prepared = session.next_statement
    if prepared > RESET_MOST_STATEMENTS:
        msg = "too many statements were left prepared to destroy"
        raise connection_failure(msg)
    connection.autocommit = False
    login = connection.authorization
    pipeline = Pipeline(connection).query("ROLLBACK")
    for number in range(prepared):
        pipeline.release(number)
    pipeline.query(f"SET SESSION AUTHORIZATION {_delimited(login)}")
    pipeline.query(f"SET SCHEMA {_delimited(login)}")
    pipeline.query("SET TIME ZONE LOCAL")
    for sql in more:
        pipeline.query(sql)
    outcomes = pipeline.run()
    releases = prepared * 2
    for outcome in [*outcomes[:1], *outcomes[1 + releases :]]:
        if isinstance(outcome, Error):
            raise outcome
    session.next_statement = 0
