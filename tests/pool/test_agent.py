"""Tests of the SQL-agent, its statements read as Turborel's parser reads them."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import pytest

from turborel import (
    Error,
    InternalError,
    NotSupportedError,
    OperationalError,
    ProgrammingError,
)
from turborel._errors import connection_failure
from turborel._pool.agent import identifier, parse
from turborel.client import Agent, Complete

if TYPE_CHECKING:
    from turborel.client import Connection, Sink


@dataclass
class Fake:
    """A connection that answers the agent as told."""

    server: str | None
    user: str | None
    in_transaction: bool = False
    is_lost: bool = False
    warning: str | None = None
    fail_terminate: bool = False
    ran: list[str] = field(default_factory=list)
    ended: bool = False

    def query(self, sql: str) -> str:
        """`sql`, as if run."""
        self.ran.append(sql)
        return sql

    def query_into(self, sql: str, _: object) -> int:
        """None of `sql`'s rows."""
        self.ran.append(sql)
        return 0

    def canceller(self) -> None:
        """No canceller."""

    def terminate(self) -> None:
        """Ended, or a failure as told."""
        self.ended = True
        if self.fail_terminate:
            raise connection_failure("cannot end")


class Connector:
    """A connector of fakes, refusing the servers it is told to."""

    def __init__(self) -> None:
        """A connector of none yet."""
        self.made: list[Fake] = []
        self.unreachable: set[str] = set()
        self.refusing: set[str] = set()

    def __call__(self, server: str | None, user: str | None) -> Connection:
        """A fake connection to `server` as `user`."""
        if server in self.unreachable:
            raise connection_failure(f"cannot reach {server}")
        if server in self.refusing:
            raise OperationalError("refused", sqlcode=-919, sqlstate="28000")
        fake = Fake(server, user)
        self.made.append(fake)
        return cast("Connection", fake)


@pytest.mark.parametrize(
    ("sql", "message", "position"),
    [
        ("CONNECT db", "expected TO, found DB", 8),
        ("CONNECT TO db1", "expected a <literal>, found DB1", 11),
        ("DISCONNECT", "expected a <literal>, found end of statement", 10),
        ("CONNECT TO 'a' 'b'", "expected end of statement, found 'b'", 15),
        ("CONNECT TO 'a' 12", "expected end of statement, found 12", 15),
        ("CONNECT TO 'a' AS", "expected a <literal>, found end of statement", 17),
        ("CONNECT TO ?", 'expected a <literal>, found "?"', 11),
        ("DISCONNECT ALL extra", "expected end of statement, found EXTRA", 15),
        ("SET CONNECTION", "expected a <literal>, found end of statement", 14),
        ("CONNECT TO 'a' + 1", 'expected end of statement, found "+"', 15),
        ('CONNECT TO "q"', "expected a <literal>, found q", 11),
        ("CONNECT TO 'a'||'b'", 'expected end of statement, found "||"', 14),
    ],
)
def test_a_connection_statement_that_breaks_its_syntax(
    sql: str, message: str, position: int
) -> None:
    """Verifies: [CLIENT The SQL-agent] connection statements, parsed.

    One that breaks its syntax refused (SQLCODE -102, SQLSTATE 42000),
    its message and position turborel-client's.
    """
    with pytest.raises(ProgrammingError) as broken:
        parse(sql)
    assert (broken.value.sqlcode, broken.value.sqlstate) == (-102, "42000")
    assert (broken.value.message, broken.value.position) == (message, position)


def test_what_is_and_is_not_a_connection_statement() -> None:
    """Verifies: [CLIENT The SQL-agent] other statements, sent on.

    A connection statement's names its literals; a name an identifier,
    regular ones in upper case.
    """
    assert parse("SELECT 1") is None
    assert parse("SET SCHEMA 'A'") is None
    assert parse("") is None
    statement = parse("connect to N'db' as 'two' user 'ann' -- a comment\n;")
    assert statement is not None
    assert (statement.verb, statement.target) == ("connect", "")
    for sql, verb, target in [
        ("CONNECT TO DEFAULT", "connect default", ""),
        ("SET CONNECTION DEFAULT", "set", ""),
        ("DISCONNECT DEFAULT", "disconnect", "default"),
        ("DISCONNECT CURRENT /* now */", "disconnect", "current"),
        ("DISCONNECT 'one'", "disconnect", "named"),
    ]:
        found = parse(sql)
        assert found is not None
        assert (found.verb, found.target) == (verb, target)
    assert (
        identifier("two"),
        identifier('"Two"'),
        identifier("a b"),
        identifier("select"),
    ) == (
        "TWO",
        "Two",
        None,
        None,
    )
    with pytest.raises(Error, match="unterminated"):
        parse("CONNECT TO 'open")


def test_connect_set_and_disconnect() -> None:
    """Verifies: [CLIENT The SQL-agent] connections, named, one current.

    CONNECT through the connector to the address and as the user it
    names; SET CONNECTION; DISCONNECT; every other statement to the
    current connection.
    """
    connector = Connector()
    agent = Agent(connector)
    with pytest.raises(OperationalError) as none:
        agent.query("VALUES 1")
    assert (none.value.sqlstate, none.value.rule) == (
        "08003",
        "ISO/IEC 9075:1992 §15.3 GR9",
    )
    done = agent.query("CONNECT TO 'db1' AS 'one' USER 'ann'")
    assert isinstance(done, Complete)
    assert (connector.made[0].server, connector.made[0].user, agent.current_name) == (
        "db1",
        "ann",
        "ONE",
    )
    agent.query("CONNECT TO 'db2'")
    names: list[object] = [agent.current_name]
    ran: object = agent.query("VALUES 2")
    sink = cast("Sink", object())
    assert (names, ran, agent.query_into("VALUES 3", sink)) == (["DB2"], "VALUES 2", 0)
    agent.query("SET CONNECTION 'one'")
    assert agent.current_connection is cast("Connection", connector.made[0])
    agent.query("DISCONNECT 'one'")
    gone: list[object] = [agent.current_name, agent.current_connection]
    assert (gone, connector.made[0].ended) == ([None, None], True)
    agent.query("CONNECT TO DEFAULT")
    default: list[object] = [agent.current_name, connector.made[-1].server]
    assert default == [None, None]
    assert (agent.warning, agent.is_lost, agent.canceller()) == (None, False, None)
    agent.query("DISCONNECT CURRENT")
    assert agent.query_into("CONNECT TO 'db3'", sink) == agent.query(
        "SET CONNECTION 'db3'"
    )
    agent.terminate()
    assert all(f.ended for f in connector.made)


def test_the_rules_of_each_statement() -> None:
    """Verifies: [CLIENT The SQL-agent] each rule of §15 a connection statement keeps.

    In an active transaction none (0A001); a user no authorization
    identifier (28000); a name no identifier (2E000) or in use (08002); a
    server unreachable (08001) or refusing (08004); no such connection
    (08003); one ending in a transaction (25000); one failing to end a
    warning, 01002.
    """
    connector = Connector()
    connector.unreachable.add("far")
    connector.refusing.add("shut")
    agent = Agent(connector, cast("Connection", Fake("first", None)))
    cases: list[tuple[str, type[Error], str]] = [
        ("CONNECT TO 'x' USER 'not a user'", OperationalError, "28000"),
        ("CONNECT TO 'x' AS 'a b'", ProgrammingError, "2E000"),
        ("CONNECT TO DEFAULT", OperationalError, "08002"),
        ("CONNECT TO 'far'", OperationalError, "08001"),
        ("CONNECT TO 'shut'", OperationalError, "08004"),
        ("SET CONNECTION 'none'", OperationalError, "08003"),
        ("DISCONNECT 'none'", OperationalError, "08003"),
        ("CONNECT TO 42", ProgrammingError, "42000"),
    ]
    for sql, kind, sqlstate in cases:
        with pytest.raises(kind) as refused:
            agent.query(sql)
        assert refused.value.sqlstate == sqlstate, sql
    with pytest.raises(OperationalError) as privilege:
        agent.query("CONNECT TO 'x' USER 'not a user'")
    assert privilege.value.sqlcode == -104
    agent.query("CONNECT TO 'db2'")
    connector.made[-1].in_transaction = True
    with pytest.raises(NotSupportedError) as spanning:
        agent.query("SET CONNECTION DEFAULT")
    assert spanning.value.sqlstate == "0A001"
    with pytest.raises(InternalError) as active:
        agent.query("DISCONNECT ALL")
    assert active.value.sqlstate == "25000"
    connector.made[-1].in_transaction = False
    connector.made[-1].fail_terminate = True
    warned = agent.query("DISCONNECT 'db2'")
    assert isinstance(warned, Complete)
    assert warned.sqlstate == "01002"
    assert agent.current_connection is None
    with pytest.raises(OperationalError) as current:
        agent.query("DISCONNECT CURRENT")
    assert current.value.sqlstate == "08003"
    agent.query("SET CONNECTION DEFAULT")
    agent.query("CONNECT TO 'third'")
    connector.made[-1].fail_terminate = True
    with pytest.raises(OperationalError, match="cannot end"):
        agent.terminate()
