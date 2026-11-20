"""Tests of a session over a peer of the test's own: login, status, notices, ping."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from tests.kit import (
    Peer,
    complete,
    description,
    error,
    frame,
    notice,
    ready,
    rows,
    status,
    text,
)

from turborel import OperationalError, ProgrammingError
from turborel._codec.requests import HELLO
from turborel._statements.queries import Rowset
from turborel.client import Connection, Mechanism, Offer, Trust

if TYPE_CHECKING:
    from turborel._codec.failures import Notice


class Answering(Mechanism):
    """A mechanism of the test's own: it answers each challenge with its reverse."""

    NAME = "answering"

    def __init__(self) -> None:
        """Note what the session calls."""
        self.calls: list[str] = []

    def initial(self) -> bytes:
        """Its first bytes."""
        return b"first"

    def answer(self, challenge: bytes) -> bytes:
        """The challenge, reversed."""
        self.calls.append("answer")
        return challenge[::-1]

    def ready(self) -> None:
        """Noted."""
        self.calls.append("ready")

    def refused(self) -> None:
        """Noted."""
        self.calls.append("refused")


def test_a_login_reads_statuses_then_ready() -> None:
    """Verifies: [PROTOCOL Opening a connection] Hello, Statuses, then Ready.

    [PROTOCOL Ready 'R'] authorization, key, capabilities, server;
    [CLIENT What the server tells] each setting as Status told it.
    """
    with Peer() as peer:
        peer.reply(
            status("AUTHORIZATION", "ANN"), ready(capabilities=("status", "ping"))
        )
        conn = Connection.open(peer.client, "ann", Trust())
        kind, body = peer.received()
        assert kind == HELLO
        assert text("ann") in body
        assert (conn.authorization, conn.server) == ("ANN", "turborel 0.0.0 (alpha)")
        assert conn.granted == ("status", "ping")
        assert conn.setting("AUTHORIZATION") == "ANN"
        assert conn.target is None
        assert conn.canceller() is None
        assert "ANN" in repr(conn)


def test_each_challenge_is_answered_until_ready() -> None:
    """Verifies: [PROTOCOL Opening a connection] Challenge and Answer, step by step.

    [PROTOCOL Answer 'A'] the client's answer to each; the mechanism told
    of Ready.
    """
    mechanism = Answering()
    with Peer() as peer:
        peer.reply(frame("C", text("abc")[0:4] + b"abc"), ready())
        Connection.open(peer.client, "ANN", mechanism)
        peer.received()
        kind, body = peer.received()
        assert (kind, body) == (ord("A"), b"\x03\x00\x00\x00cba")
    assert mechanism.calls == ["answer", "ready"]


def test_a_refused_login_raises_the_server_s_failure() -> None:
    """Verifies: [PROTOCOL Opening a connection] refused: an Error, then the close.

    [PROTOCOL Error 'E'] class 28 as the connection is made ends it; the
    mechanism told it was refused.
    """
    mechanism = Answering()
    with Peer() as peer:
        peer.reply(error(-919, "28000", "the user or the password is wrong"))
        with pytest.raises(OperationalError) as failure:
            Connection.open(peer.client, "ANN", mechanism)
    assert (failure.value.sqlcode, failure.value.sqlstate) == (-919, "28000")
    assert failure.value.failure is not None
    assert mechanism.calls == ["refused"]


@pytest.mark.parametrize(
    "out_of_turn", [rows((True,)), frame("G"), frame("z", b"\x00")]
)
def test_a_login_that_gets_no_ready_loses_the_connection(out_of_turn: bytes) -> None:
    """Verifies: [PROTOCOL Opening a connection] a reply out of turn fails the login.

    [PROTOCOL Compressed frames] a `z` frame when compression was not
    granted fails the connection (08006).
    """
    with Peer() as peer:
        peer.reply(out_of_turn)
        with pytest.raises(OperationalError) as failure:
            Connection.open(peer.client, "ANN", Trust())
    assert failure.value.sqlstate == "08006"


def test_notices_are_kept_or_handed_to_a_handler() -> None:
    """Verifies: [CLIENT What the server tells] notices: a handler, or the last 64 kept.

    [PROTOCOL Notice 'N'] each before the statement's completion.
    """
    with Peer() as peer:
        peer.reply(ready(capabilities=("ping",)))
        conn = Connection.open(peer.client, "ANN", Trust())
        peer.reply(*(notice("01000", str(n)) for n in range(65)), frame("G"))
        conn.ping()
        kept = conn.take_notices()
        assert len(kept) == 64
        assert kept[0].message == "1"
        assert conn.take_notices() == []
        heard: list[Notice] = []
        conn.set_notice_handler(heard.append)
        peer.reply(notice("01T01", "rolled back"), frame("G"))
        conn.ping()
        assert [n.sqlstate for n in heard] == ["01T01"]
        assert conn.take_notices() == []


def test_ping_needs_its_capability_and_its_pong() -> None:
    """Verifies: [CLIENT What a connection asks for] a method needing a capability.

    Not granted, it fails before it sends anything (08006) and the
    connection goes on [PROTOCOL Ping 'G'] [PROTOCOL Pong 'G']; an Error
    to it is raised; a reply that is no Pong loses the connection.
    """
    with Peer() as peer:
        peer.reply(ready())
        conn = Connection.open(peer.client, "ANN", Trust(), Offer.none())
        with pytest.raises(OperationalError):
            conn.ping()
        assert not conn.is_lost
    with Peer() as peer:
        peer.reply(ready(capabilities=("ping",)))
        conn = Connection.open(peer.client, "ANN", Trust())
        peer.reply(error(-910, "42000", "no"))
        with pytest.raises(ProgrammingError):
            conn.ping()
        peer.reply(complete())
        with pytest.raises(OperationalError):
            conn.ping()
        assert conn.is_lost
        with pytest.raises(OperationalError):
            conn.query("VALUES 1")


def test_a_query_gives_its_rows_or_its_completion() -> None:
    """Verifies: [CLIENT Running statements] a query's columns and rows, or completion.

    [PROTOCOL Query 'Q'] a Description, its Rows and a Complete, or a
    Complete alone, or an Error; [CLIENT Running statements]
    `in_transaction` as the server last said.
    """
    with Peer() as peer:
        peer.reply(ready())
        conn = Connection.open(peer.client, "ANN", Trust())
        peer.reply(
            description("A"), rows((True,)), rows((False,)), complete(active=True)
        )
        outcome = conn.query("SELECT A FROM T")
        assert isinstance(outcome, Rowset)
        assert (outcome.rows, conn.in_transaction) == ([(True,), (False,)], True)
        peer.reply(complete("01000"))
        done = conn.query("UPDATE T SET A = TRUE")
        assert (done, conn.in_transaction) == (complete_of("01000"), False)
        peer.reply(error(-103, "2A000", "no table", active=True))
        with pytest.raises(ProgrammingError):
            conn.query("SELECT * FROM NOPE")
        assert (conn.in_transaction, conn.is_lost) == (True, False)


def complete_of(sqlstate: str) -> object:
    """The Complete reply of `sqlstate`, decoded."""
    from turborel._codec.replies import Complete  # noqa: PLC0415  # One test's.

    return Complete(0, sqlstate, active=False)


@pytest.mark.parametrize(
    "replies",
    [
        (frame("G"),),
        (description("A"), frame("G")),
    ],
)
def test_a_query_answered_out_of_turn_loses_the_connection(
    replies: tuple[bytes, ...],
) -> None:
    """Verifies: [PROTOCOL Conversations] a statement's replies in a fixed order.

    One out of it loses the connection (08006).
    """
    with Peer() as peer:
        peer.reply(ready())
        conn = Connection.open(peer.client, "ANN", Trust())
        peer.reply(*replies)
        with pytest.raises(OperationalError):
            conn.query("VALUES 1")
        assert conn.is_lost


def test_a_statement_s_replies_in_their_order() -> None:
    """Verifies: [PROTOCOL Conversations] Rows, Notices, Statuses, Complete.

    Each Notice and Status taken as it comes, the statement's last reply
    its outcome.
    """
    with Peer() as peer:
        peer.reply(ready())
        conn = Connection.open(peer.client, "ANN", Trust())
        peer.reply(
            description("A"),
            rows((True,)),
            notice("01004", "truncated"),
            status("SESSION.TIME_ZONE", "+01:00"),
            complete("01004"),
        )
        outcome = conn.query("SELECT A FROM T")
        assert isinstance(outcome, Rowset)
        assert outcome.rows == [(True,)]
        assert [n.sqlstate for n in conn.take_notices()] == ["01004"]
        assert conn.setting("SESSION.TIME_ZONE") == "+01:00"
