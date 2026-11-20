"""Live tests of pipelines, pools and the SQL-agent."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from turborel import IntegrityError, ProgrammingError
from turborel.client import (
    PIPELINE_WINDOW,
    SKIPPED,
    Agent,
    Complete,
    Local,
    Offer,
    OnError,
    Pool,
    PoolConfig,
    Rowset,
    Trust,
    connect_local,
    connect_to,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from live import Live

    from turborel.client import Connection


@pytest.fixture
def conn(live: Live) -> Iterator[Connection]:
    """A connection by trust over the live server's socket."""
    connection = connect_local(live.socket, "ANN", Trust())
    yield connection
    if not connection.is_lost:
        connection.terminate()


def test_a_pipeline_s_outcomes(conn: Connection) -> None:
    """Verifies: [CLIENT Pipelines] one outcome each, in order.

    [PROTOCOL Requests] requests sent before the last is answered; a
    failure its request's own, those after it run; written a window at a
    time; under autocommit, each its own transaction.
    """
    conn.query("CREATE TABLE PIPED (N INTEGER PRIMARY KEY, S CLOB(1M))")
    conn.query("COMMIT")
    insert = conn.prepare("INSERT INTO PIPED VALUES (?, ?)")
    conn.autocommit = True
    long = "x" * PIPELINE_WINDOW
    outcomes = (
        conn.pipeline()
        .execute(insert, (1, "a"))
        .execute(insert, (1, "again"))
        .execute(insert, (2, long))
        .query("SELECT COUNT(*) FROM PIPED")
        .run()
    )
    assert isinstance(outcomes[0], Complete)
    assert isinstance(outcomes[1], IntegrityError)
    assert isinstance(outcomes[2], Complete)
    assert isinstance(outcomes[3], Rowset)
    assert outcomes[3].rows == [(2,)]
    assert not conn.in_transaction


def test_a_skipping_batch(conn: Connection) -> None:
    """Verifies: [CLIENT Pipelines] skip on error, undone and skipped.

    A skipping batch one transaction, committed as it ends under
    autocommit where it began none.
    """
    conn.query("CREATE TABLE SKIPPED (N INTEGER PRIMARY KEY)")
    conn.query("COMMIT")
    insert = conn.prepare("INSERT INTO SKIPPED VALUES (?)")
    conn.autocommit = True
    batch = conn.pipeline().on_error(OnError.SKIP)
    outcomes = (
        batch.execute(insert, (5,)).execute(insert, (5,)).execute(insert, (6,)).run()
    )
    assert isinstance(outcomes[0], Complete)
    assert isinstance(outcomes[1], IntegrityError)
    assert outcomes[2] is SKIPPED
    assert getattr(conn.query("SELECT N FROM SKIPPED"), "rows") == [(5,)]  # noqa: B009
    assert not conn.in_transaction


def test_a_pool_of_connections(live: Live) -> None:
    """Verifies: [CLIENT Pools] a bounded set of connections, given back reset.

    By Reset, autocommit off, then the `reset` statements; checked by
    Ping; a connection's settings and prepared statements gone for the
    next borrower.
    """
    pool = Pool(
        lambda: connect_local(live.socket, "ANN", Trust()),
        PoolConfig(max=2, reset=("SET TIME ZONE INTERVAL '+01:00' HOUR TO MINUTE",)),
    )
    with pool:
        with pool.get() as first:
            first.autocommit = True
            first.query("SET TIME ZONE INTERVAL '+03:00' HOUR TO MINUTE")
            first.prepare("VALUES 1")
        with pool.get() as again:
            assert again.setting("SESSION.TIME_ZONE") == "+01:00"
            assert again.autocommit is False
        assert pool.counts() == (1, 1)
    assert pool.counts() == (0, 0)


def test_a_pool_of_a_server_granting_neither(live: Live) -> None:
    """Verifies: [CLIENT Pools] of a server that takes neither, ROLLBACK and a pipeline.

    The check ROLLBACK; the reset one pipeline: the transaction rolled
    back, the statements prepared closed and destroyed, the user, schema
    and zone those of the login.
    """
    pool = Pool(
        lambda: connect_to(Local(live.socket), "ANN", Trust(), offer=Offer.none())
    )
    with pool:
        with pool.get() as first:
            statement = first.prepare("VALUES 1")
            first.query("SET TIME ZONE INTERVAL '+03:00' HOUR TO MINUTE")
            first.query("CREATE TABLE LEFT_BEHIND (N INTEGER)")
        with pool.get() as again:
            with pytest.raises(ProgrammingError) as gone:
                again.execute(statement)
            assert gone.value.sqlstate == "26000"
            rows = getattr(again.query("VALUES CURRENT_USER"), "rows")  # noqa: B009
            assert rows == [("ANN",)]
            with pytest.raises(ProgrammingError):
                again.query("SELECT * FROM LEFT_BEHIND")


def test_the_sql_agent(live: Live) -> None:
    """Verifies: [CLIENT The SQL-agent] CONNECT through the program's connector.

    SET CONNECTION, DISCONNECT, and every other statement to the current
    connection.
    """

    def connector(server: str | None, user: str | None) -> Connection:
        return connect_local(server or live.socket, user or "ANN", Trust())

    agent = Agent(connector)
    agent.query(f"CONNECT TO '{live.socket}' AS 'ledger' USER 'ann'")
    assert getattr(agent.query("VALUES CURRENT_USER"), "rows") == [("ANN",)]  # noqa: B009
    agent.query("COMMIT")
    agent.query("CONNECT TO DEFAULT")
    agent.query("SET CONNECTION 'ledger'")
    assert agent.current_name == "LEDGER"
    agent.query("DISCONNECT ALL")
    assert agent.current_connection is None
