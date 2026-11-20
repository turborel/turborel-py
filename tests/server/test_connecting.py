"""Live tests of connecting: transports, mechanisms, TLS, capabilities, status."""

from __future__ import annotations

import socket
import ssl
import struct
from typing import TYPE_CHECKING

import pytest

from turborel import OperationalError
from turborel.client import (
    Certificate,
    ChannelBinding,
    Connection,
    KeyCache,
    Local,
    Offer,
    Password,
    Scram,
    Tcp,
    Timeouts,
    Tls,
    Trust,
    connect,
    connect_local,
    connect_tls,
    connect_to,
    presenting,
    roots,
    tls_channel,
    trusting,
)

if TYPE_CHECKING:
    from live import Live

DEFAULT_ASKED = (
    "notices", "status", "diagnostics", "describe", "cursors", "ping", "reset",
    "change-user", "query-attributes", "connection-attributes", "multi-statement",
    "commit-position", "copy", "row-counts", "generated-values", "fetch-ends",
    "conditions", "declared-types",
)  # fmt: skip


def test_trust_over_tcp_and_what_ready_tells(live: Live) -> None:
    """Verifies: [CLIENT Connecting] connect over TCP by trust; Ready's product, user.

    [PROTOCOL The Native Protocol] TCP on its port; [PROTOCOL Mechanisms]
    trust accepted at once of a local client; [PROTOCOL Opening a
    connection] Statuses then Ready; [CLIENT What a connection asks for]
    every capability but compression asked for, granted in the table's
    order.
    """
    conn = connect((live.host, live.port), "ann", Trust())
    assert conn.authorization == "ANN"
    assert conn.server.startswith("turborel ")
    assert conn.granted == DEFAULT_ASKED
    assert conn.target == Tcp(live.host, live.port)
    conn.ping()
    conn.terminate()
    assert conn.is_lost


def test_the_session_s_status_is_told_at_login(live: Live) -> None:
    """Verifies: [PROTOCOL Status 'T'] a Status of each setting, as login begins.

    AUTHORIZATION, SCHEMA, READ_ONLY, SERVER_VERSION, SERVER_READ_ONLY,
    CATALOG and OWNER, and every setting a session may set for itself;
    [CLIENT What the server tells] each read with no round trip.
    """
    conn = connect((live.host, live.port), "ANN", Trust())
    told = conn.settings()
    assert told["AUTHORIZATION"] == "ANN"
    assert told["SCHEMA"] == "ANN"
    assert told["READ_ONLY"] == "NO"
    assert told["SERVER_VERSION"] == conn.server
    assert told["SERVER_READ_ONLY"] == "NO"
    assert told["CATALOG"]
    assert told["OWNER"] == "YES"
    assert conn.setting("SESSION.TIME_ZONE") == "+00:00"
    assert "TRANSACTION.ISOLATION" in told
    conn.query("SET TIME ZONE INTERVAL '+02:00' HOUR TO MINUTE")
    assert conn.setting("SESSION.TIME_ZONE") == "+02:00"
    assert conn.setting("NO.SUCH") is None
    conn.terminate()


def test_an_offer_of_none_sees_the_first_form(live: Live) -> None:
    """Verifies: [CLIENT What a connection asks for] an offer of none; what was granted.

    [PROTOCOL The Native Protocol] a client that asks for none sees the
    first form: no Status, nothing granted; a method needing a capability
    not granted fails before it sends anything, the connection kept.
    """
    conn = connect_to(Tcp(live.host, live.port), "ANN", Trust(), offer=Offer.none())
    assert conn.granted == ()
    assert conn.settings() == {}
    with pytest.raises(OperationalError) as failure:
        conn.ping()
    assert "did not grant ping" in failure.value.message
    assert not conn.is_lost
    conn.terminate()


def test_compression_and_attributes_offered(live: Live) -> None:
    """Verifies: [CLIENT What a connection asks for] compression and attributes offered.

    [PROTOCOL Capabilities] `compression` granted when asked for, frames
    then compressed both ways past their thresholds; `connection-attributes`,
    the program's attributes in Hello.
    """
    offer = Offer(compress_from=64).compressed().attribute("application", "pytest")
    conn = connect_to(Tcp(live.host, live.port), "ANN", Trust(), offer=offer)
    assert "compression" in conn.granted
    rows = conn.query(
        "SELECT ATTRIBUTE_VALUE FROM INFORMATION_SCHEMA.CONNECTION_ATTRIBUTES"
        " WHERE ATTRIBUTE_NAME = 'application'"
    )
    assert getattr(rows, "rows") == [("pytest",)]  # noqa: B009  # A rowset.
    big = conn.query("VALUES '" + "x" * 5000 + "'")
    assert getattr(big, "rows") == [("x" * 5000,)]  # noqa: B009
    conn.terminate()


def test_a_local_socket(live: Live) -> None:
    """Verifies: [CLIENT Connecting] connect over a Unix socket.

    [PROTOCOL The Native Protocol] a Unix socket where the operator asks;
    [PROTOCOL Mechanisms] `password` and SCRAM over it.
    """
    conn = connect_local(live.socket, "ANN", Trust())
    assert conn.target == Local(live.socket)
    conn.terminate()
    connect_local(live.socket, "ANN", Password(live.password)).terminate()
    connect_local(live.socket, "ANN", Scram(live.password)).terminate()


def test_secrets_are_refused_over_plain_tcp(live: Live) -> None:
    """Verifies: [CLIENT Connecting] a password, or SCRAM, refused over plain TCP.

    SQLSTATE 28000, before connecting; SCRAM asked for in the clear goes,
    where the server takes it so.
    """
    for mechanism in (Password(live.password), Scram(live.password)):
        with pytest.raises(OperationalError) as failure:
            connect((live.host, live.port), "ANN", mechanism)
        assert failure.value.sqlstate == "28000"
    clear = Scram(live.password, in_the_clear=True)
    connect((live.host, live.port), "ANN", clear).terminate()


def test_scram_proves_the_password_and_its_cache_hits(live: Live) -> None:
    """Verifies: [CLIENT The SCRAM key cache] a later login of the same salt hits.

    [PROTOCOL Mechanisms] scram-sha-256: client-first, server-first,
    client-final, server-final, an empty Answer; a wrong password refused
    (28000) and its keys forgotten.
    """
    cache = KeyCache()
    connect_local(live.socket, "ANN", Scram(live.password, cache=cache)).terminate()
    connect_local(live.socket, "ANN", Scram(live.password, cache=cache)).terminate()
    assert cache.lookups() == (1, 1)
    with pytest.raises(OperationalError) as failure:
        connect_local(live.socket, "ANN", Scram("wrong", cache=cache))
    assert failure.value.sqlstate == "28000"
    assert len(cache) == 1


def test_tls_and_scram_sha_256_plus(live: Live) -> None:
    """Verifies: [CLIENT Connecting] connect to a target over TLS; SCRAM-PLUS bound.

    [PROTOCOL The Native Protocol] TLS begun on the same port;
    [PROTOCOL Mechanisms] scram-sha-256-plus by tls-server-end-point, and
    `password` over TLS; a certificate of an authority not trusted fails
    the handshake (08006).
    """
    context = trusting(live.ca)
    scram = Scram(live.password)
    conn = connect_tls(
        (live.host, live.port), context, "ANN", scram, server_name="localhost"
    )
    assert isinstance(conn.target, Tls)
    conn.terminate()
    connect_tls(
        (live.host, live.port), context, "ANN", Password(live.password), "localhost"
    ).terminate()
    with pytest.raises(OperationalError) as failure:
        connect_tls(
            (live.host, live.port), trusting(live.stranger), "ANN", Trust(), "localhost"
        )
    assert failure.value.sqlstate == "08006"
    assert "handshake" in failure.value.message


@pytest.mark.parametrize("version", [ssl.TLSVersion.TLSv1_3, ssl.TLSVersion.TLSv1_2])
def test_scram_plus_binds_by_the_server_s_certificate(
    live: Live, version: ssl.TLSVersion
) -> None:
    """Verifies: [PROTOCOL Mechanisms] scram-sha-256-plus, its channel bound.

    [CLIENT Connecting] SCRAM-SHA-256-PLUS over TLS 1.3 and over TLS 1.2,
    bound by tls-server-end-point, the certificate the server presented,
    as Python's ssl exports no keying material for tls-exporter (RULES.md
    D8); a binding required and made, the server accepting it.
    """
    context = trusting(live.ca)
    context.minimum_version = context.maximum_version = version
    scram = Scram(live.password, channel_binding=ChannelBinding.REQUIRE)
    conn = connect_tls((live.host, live.port), context, "ANN", scram, "localhost")
    assert conn.authorization == "ANN"
    conn.terminate()


def test_a_client_certificate_proves_its_user(live: Live) -> None:
    """Verifies: [CLIENT Connecting] certificate: a TLS client certificate presented.

    [PROTOCOL Mechanisms] `certificate`, by the TLS client certificate's
    common name.
    """
    context = presenting(live.ca, live.client_certificate, live.client_key)
    conn = connect_tls(
        (live.host, live.port), context, "ANN", Certificate(), "localhost"
    )
    assert conn.authorization == "ANN"
    conn.terminate()


def raw_hello(live: Live, hello: bytes) -> bytes:
    """What the server answers a Hello of the test's own, read to its close."""
    with socket.create_connection((live.host, live.port), timeout=10) as raw:
        raw.sendall(b"H" + struct.pack("<I", len(hello)) + hello)
        answer = b""
        while chunk := raw.recv(4096):
            answer += chunk
    return answer


def text(s: str) -> bytes:
    """A string field."""
    return struct.pack("<I", len(s.encode())) + s.encode()


@pytest.mark.parametrize(
    ("hello", "sqlstate"),
    [
        (struct.pack("<I", 2) + text("ANN") + text("trust") + bytes(8), b"08004"),
        (struct.pack("<I", 1) + text("ANN SMITH") + text("trust") + bytes(8), b"28000"),
        (struct.pack("<I", 1) + text("ANN") + text("nope") + bytes(8), b"28000"),
    ],
)
def test_a_login_the_server_refuses_before_any_exchange(
    live: Live, hello: bytes, sqlstate: bytes
) -> None:
    """Verifies: [PROTOCOL Opening a connection] another version, user or mechanism.

    A version other than 1 refused (08004); a user not an identifier, or a
    mechanism not served, refused before any exchange (28000); refused,
    an Error, and the server closes.
    """
    answer = raw_hello(live, hello)
    assert answer[:1] == b"E"
    assert sqlstate in answer


def test_a_wrong_password_is_refused_and_ends_the_connection(live: Live) -> None:
    """Verifies: [PROTOCOL Error 'E'] an Error of class 28 at login ends the connection.

    [PROTOCOL Opening a connection] refused: an Error, then the server
    closes; the driver's exception carries SQLCODE -919 and 28000.
    """
    with pytest.raises(OperationalError) as failure:
        connect_local(live.socket, "ANN", Password("wrong"))
    assert (failure.value.sqlcode, failure.value.sqlstate) == (-919, "28000")


def test_timeouts_bound_the_waits(live: Live) -> None:
    """Verifies: [CLIENT Timeouts] the program's own timeouts; the read timeout changed.

    A wait that runs out loses the connection (08006), saying the server
    did not answer in time.
    """
    conn = connect_to(
        Tcp(live.host, live.port), "ANN", Trust(), Timeouts(connect=5, read=5)
    )
    assert conn.read_timeout == 5
    holder = connect((live.host, live.port), "ANN", Trust())
    holder.query("CREATE TABLE TIMED (N INTEGER)")
    holder.query("INSERT INTO TIMED VALUES (1)")
    holder.query("COMMIT")
    holder.query("UPDATE TIMED SET N = 2")
    conn.set_read_timeout(0.3)
    with pytest.raises(OperationalError) as failure:
        conn.query("UPDATE TIMED SET N = 3")
    assert "did not answer in time" in failure.value.message
    assert conn.is_lost
    holder.query("ROLLBACK")
    holder.terminate()


def test_a_cancel_fails_the_running_statement(live: Live) -> None:
    """Verifies: [PROTOCOL Cancel 'Z'] the key Ready gave, on a connection of its own.

    The statement cancelled fails with SQLCODE -920 and SQLSTATE TB920;
    [CLIENT Running statements] from another thread, within 10 seconds.
    """
    import threading  # noqa: PLC0415  # This test alone starts a thread.

    holder = connect((live.host, live.port), "ANN", Trust())
    holder.query("CREATE TABLE HELD (N INTEGER)")
    holder.query("INSERT INTO HELD VALUES (1)")
    holder.query("COMMIT")
    holder.query("UPDATE HELD SET N = 2")
    waiter = connect((live.host, live.port), "ANN", Trust())
    canceller = waiter.canceller()
    assert canceller is not None
    assert "key" not in repr(canceller)
    caught: list[BaseException] = []

    def wait() -> None:
        try:
            waiter.query("UPDATE HELD SET N = 3")
        except OperationalError as e:
            caught.append(e)

    thread = threading.Thread(target=wait)
    thread.start()
    running = (
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.CONNECTIONS WHERE STATE = 'RUNNING'"
    )
    while thread.is_alive() and getattr(holder.query(running), "rows") == [(1,)]:  # noqa: B009
        pass
    while thread.is_alive():
        canceller.cancel()
        thread.join(timeout=0.5)
    assert len(caught) == 1
    error = caught[0]
    assert isinstance(error, OperationalError)
    assert (error.sqlcode, error.sqlstate) == (-920, "TB920")
    holder.query("ROLLBACK")
    holder.terminate()
    waiter.terminate()


def test_a_reply_past_the_body_taken_loses_the_connection(live: Live) -> None:
    """Verifies: [CLIENT Timeouts] replies taken up to the bytes the program says.

    A longer one loses the connection (08006) [PROTOCOL Frames].
    """
    conn = connect((live.host, live.port), "ANN", Trust())
    conn.set_max_body(16)
    with pytest.raises(OperationalError) as failure:
        conn.query("VALUES 'a string longer than sixteen bytes'")
    assert failure.value.sqlstate == "08006"
    assert conn.is_lost
    with pytest.raises(OperationalError):
        conn.ping()


def test_terminate_commits_as_commit_at_end_says(live: Live) -> None:
    """Verifies: [PROTOCOL Terminate 'X'] the session ends, its transaction committed.

    [CLIENT Connecting] SESSION.COMMIT_AT_END ON by default, so a row
    inserted and never committed is there after terminate.
    """
    conn = connect((live.host, live.port), "ANN", Trust())
    conn.query("CREATE TABLE ENDED (N INTEGER)")
    conn.query("COMMIT")
    conn.query("INSERT INTO ENDED VALUES (7)")
    assert conn.in_transaction
    conn.terminate()
    after = connect((live.host, live.port), "ANN", Trust())
    assert getattr(after.query("SELECT N FROM ENDED"), "rows") == [(7,)]  # noqa: B009
    after.terminate()


def test_a_tls_stream_the_program_opened(live: Live) -> None:
    """Verifies: [CLIENT Connecting] a TLS stream the program opened, bound first.

    The program binds SCRAM to the stream's channel, so SCRAM-SHA-256-PLUS
    proves the password over it.
    """
    context = trusting(live.ca)
    raw = socket.create_connection((live.host, live.port), timeout=10)
    secured = context.wrap_socket(raw, server_hostname="localhost")
    scram = Scram(live.password)
    scram.bind(tls_channel(secured))
    assert scram.name == "scram-sha-256-plus"
    conn = Connection.open(secured, "ANN", scram)
    assert conn.authorization == "ANN"
    conn.terminate()


def test_the_platform_s_authorities_trusted_too(
    live: Live, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifies: [CLIENT Connecting] a file's authorities, the platform's, or both.

    SSL_CERT_FILE names the file the platform's authorities are read from
    instead, where set.
    """
    both = roots(live.ca, platform=True)
    connect_tls((live.host, live.port), both, "ANN", Trust(), "localhost").terminate()
    monkeypatch.setenv("SSL_CERT_FILE", live.ca)
    platform = roots(platform=True)
    connect_tls(
        (live.host, live.port), platform, "ANN", Trust(), "localhost"
    ).terminate()


def test_reset_and_change_user_tell_the_settings_again(live: Live) -> None:
    """Verifies: [PROTOCOL Status 'T'] a Status of each after Reset or ChangeUser.

    After a statement, one of each it changed; [PROTOCOL Reset 'W'] the
    transaction rolled back, a Notice of 01T01 first, settings at the
    database's value; [PROTOCOL ChangeUser 'U'] the session renewed under
    the user proved again.
    """
    conn = connect_local(live.socket, "ANN", Trust())
    conn.query("SET TIME ZONE INTERVAL '+03:00' HOUR TO MINUTE")
    assert conn.setting("SESSION.TIME_ZONE") == "+03:00"
    conn.query("CREATE TABLE RESET_ME (N INTEGER)")
    conn.reset()
    assert conn.setting("SESSION.TIME_ZONE") == "+00:00"
    assert [n.sqlstate for n in conn.take_notices()] == ["01T01"]
    assert not conn.in_transaction
    conn.change_user("ANN", Scram(live.password))
    assert conn.authorization == "ANN"
    assert conn.setting("AUTHORIZATION") == "ANN"
    conn.terminate()


STATUS_NAMES = (
    "SERVER_VERSION",
    "AUTHORIZATION",
    "SCHEMA",
    "READ_ONLY",
    "SERVER_READ_ONLY",
    "CATALOG",
    "OWNER",
)


def test_the_statuses_in_their_order(live: Live) -> None:
    """Verifies: [PROTOCOL Status 'T'] at login, one of each name in the page's order.

    Then the session's own settings; after a statement only what it
    changed, none of one that changed nothing, the first after login too;
    CATALOG, the catalog's name, never empty, after Reset too.
    """
    conn = connect_local(live.socket, "ANN", Trust())
    names = list(conn.settings())
    assert tuple(names[: len(STATUS_NAMES)]) == STATUS_NAMES
    assert {"SESSION.TIME_ZONE", "TRANSACTION.ISOLATION"} <= set(
        names[len(STATUS_NAMES) :]
    )
    assert conn.setting("CATALOG") == "TURBOREL"
    assert (conn.setting("OWNER"), conn.setting("SERVER_READ_ONLY")) == ("YES", "NO")
    before = dict(conn.settings())
    stream = conn._stream  # noqa: SLF001  # Its frames, counted here alone.
    kinds: list[int] = []
    reading = stream.read_frame

    def counted(max_body: int) -> tuple[int, bytes]:
        frame = reading(max_body)
        kinds.append(frame[0])
        return frame

    stream.read_frame = counted  # type: ignore[method-assign]  # Counted for the test.
    conn.query("VALUES 1")
    stream.read_frame = reading  # type: ignore[method-assign]
    assert ord("T") not in kinds
    assert dict(conn.settings()) == before
    conn.query("SET TIME ZONE INTERVAL '+04:00' HOUR TO MINUTE")
    changed = {k: v for k, v in conn.settings().items() if before.get(k) != v}
    assert changed == {"SESSION.TIME_ZONE": "+04:00"}
    conn.reset()
    assert conn.setting("SESSION.TIME_ZONE") == "+00:00"
    assert conn.setting("CATALOG") == "TURBOREL"
    conn.terminate()
