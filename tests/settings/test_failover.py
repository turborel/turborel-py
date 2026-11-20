"""Tests of connecting by settings: the order of hosts, roles, TLS by mode, failures."""

from __future__ import annotations

import socket
import ssl
import threading

import pytest

from turborel import OperationalError, ProgrammingError
from turborel._codec.failures import Failure
from turborel._errors import connection_failure
from turborel._session.raising import raised
from turborel._settings.failover import (
    Role,
    _opened,
    context,
    none_kept,
    role_of,
    seed,
    shuffle,
)
from turborel.client import Options, Settings, Tcp, Tls, TlsFiles, TlsMode


def failed(sqlstate: str, message: str) -> OperationalError | ProgrammingError:
    """A failure of `sqlstate`."""
    error = raised(
        Failure(-919, sqlstate, message, None, None, active=False, diagnostics=None)
    )
    assert isinstance(error, OperationalError | ProgrammingError)
    return error


def test_hosts_are_shuffled_by_their_seed() -> None:
    """Verifies: [CLIENT Several servers] hosts in a random order for each connection.

    Each host once, in the order the seed decides, the same for the same
    seed; different seeds different orders; one host or none as it is;
    each seed the system's own.
    """
    hosts = list(range(8))

    def order(drawn: int) -> list[int]:
        each = list(hosts)
        shuffle(each, drawn)
        return each

    assert sorted(order(7)) == hosts
    assert order(7) == order(7)
    assert len({tuple(order(n)) for n in range(16)}) > 8
    one = [1]
    shuffle(one, 3)
    assert one == [1]
    shuffle([], 3)
    assert seed() != seed()


def test_no_server_kept_says_why_each_was_not() -> None:
    """Verifies: [CLIENT Several servers] with none kept, each address and why (08001).

    Of one server tried, its own failure; 28000 if the last refused the
    user; of none, 08001.
    """
    lost = connection_failure("cannot connect")
    refused = failed("28000", "no")
    assert none_kept([("a", refused)]) is refused
    both = none_kept([("a", refused), ("b", lost)])
    assert both.sqlstate == "08001"
    assert "a: no" in both.message
    assert "b: cannot connect" in both.message
    assert none_kept([("b", lost), ("a", refused)]).sqlstate == "28000"
    assert none_kept([]).sqlstate == "08001"


def test_a_server_s_role_is_read_from_replicas() -> None:
    """Verifies: [CLIENT Several servers] a role read from REPLICAS.

    A server alone, which has no REPLICAS (class 2A or 42), takes changes;
    PRIMARY is read-write, BACKUP or UNKNOWN read-only; no row, as a
    session not the owner's sees, unknown; another failure the query's.
    """
    assert role_of(None, failed("2A000", "no table")) is Role.READ_WRITE
    assert role_of(None, failed("42000", "no table")) is Role.READ_WRITE
    assert role_of([("PRIMARY",)], None) is Role.READ_WRITE
    assert role_of([("BACKUP ",)], None) is Role.READ_ONLY
    assert role_of([("UNKNOWN",)], None) is Role.READ_ONLY
    assert role_of([], None) is Role.UNKNOWN
    with pytest.raises(OperationalError):
        role_of(None, failed("08006", "lost"))
    assert Role.UNKNOWN.value == "of a role this session cannot see"


def test_tls_by_mode() -> None:
    """Verifies: [CLIENT TLS by mode] each mode's checks.

    The verifying modes need the authorities trusted; a certificate is
    presented with its key.
    """
    files = TlsFiles()
    assert context(TlsMode.DISABLE, files) is None
    for mode in (TlsMode.PREFER, TlsMode.REQUIRE):
        made = context(mode, files)
        assert made is not None
        assert (made.verify_mode, made.check_hostname) == (ssl.CERT_NONE, False)
    with pytest.raises(OperationalError, match="no certificate authority is trusted"):
        context(TlsMode.VERIFY_CA, files)
    with pytest.raises(
        OperationalError, match="presented with its key, and none is named"
    ):
        context(TlsMode.REQUIRE, TlsFiles(certificate="chain.pem"))


def test_prefer_connects_again_without_tls() -> None:
    """Verifies: [CLIENT TLS by mode] `prefer`: TLS if taken, else plain TCP.

    Connecting again after a failed handshake, over plain TCP.
    """
    listener = socket.create_server(("127.0.0.1", 0))
    port = listener.getsockname()[1]
    accepted: list[socket.socket] = []

    def serve() -> None:
        for _ in range(2):
            peer, _ = listener.accept()
            accepted.append(peer)
            if len(accepted) == 1:
                peer.recv(1024)
                peer.close()

    thread = threading.Thread(target=serve)
    thread.start()
    made = Settings.resolve_in(
        Options({"user": "ann", "tls_mode": "prefer"}), lambda _: None
    )
    tls = context(TlsMode.PREFER, TlsFiles())
    assert tls is not None
    target, stream, bound = _opened(made, Tls("127.0.0.1", tls, port), 5.0)
    thread.join(timeout=10)
    assert (isinstance(target, Tcp), bound) == (True, None)
    stream.close()
    for peer in accepted:
        peer.close()
    listener.close()
