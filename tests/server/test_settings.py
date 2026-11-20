"""Live tests of connecting by settings: TLS by mode, files, several servers, roles."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote

import pytest

from turborel import OperationalError
from turborel.client import (
    Local,
    Offer,
    Options,
    Role,
    Settings,
    Tcp,
    Tls,
    Trust,
    connect_local,
    connect_to,
    role,
)

if TYPE_CHECKING:
    from pathlib import Path

    from live import Live

    from turborel.client import Connection


def settings(uri: str, environment: dict[str, str] | None = None) -> Settings:
    """The settings of `uri`, read with an environment of the test's own."""
    return Settings.resolve_in(Options.from_uri(uri), (environment or {}).get)


def at(live: Live, query: str, *, password: bool = True) -> str:
    """A URI of the live server over TCP: ANN, the password if `password`, `query`."""
    secret = f":{quote(live.password, safe='')}" if password else ""
    return f"turborel://ANN{secret}@{live.host}:{live.port}/?{query}"


def ended(connection: Connection) -> Connection:
    """`connection`, after a statement shows it works, ended."""
    assert getattr(connection.query("VALUES 1"), "rows") == [(1,)]  # noqa: B009
    connection.terminate()
    return connection


def test_settings_connect_as_they_say(live: Live) -> None:
    """Verifies: [CLIENT Connecting by settings] connect as settings say, like a target.

    A password proved by SCRAM, over TLS by `prefer` as the server takes
    it [CLIENT TLS by mode]; the program's name sent as the connection
    attribute `application` [CLIENT Where settings come from]; one key
    cache for every connection the same settings make [CLIENT The SCRAM
    key cache].
    """
    made = settings(at(live, "application_name=ledger"))
    conn = made.connect()
    assert isinstance(conn.target, Tls)
    assert conn.authorization == "ANN"
    rows = conn.query(
        "SELECT ATTRIBUTE_VALUE FROM INFORMATION_SCHEMA.CONNECTION_ATTRIBUTES"
        " WHERE ATTRIBUTE_NAME = 'application'"
    )
    assert getattr(rows, "rows") == [("ledger",)]  # noqa: B009
    ended(conn)
    ended(made.connect())
    assert made.key_cache.lookups() == (1, 1)


def test_tls_by_mode(live: Live) -> None:
    """Verifies: [CLIENT TLS by mode] disable, require, verify-ca and verify-full.

    `verify-ca` needing the authorities trusted, its name not checked;
    `verify-full` against `server_name`, else the host's; over plain TCP
    a secret refused before anything is sent (28000) [CLIENT Connecting
    by settings]; with no password, trust.
    """
    with pytest.raises(OperationalError) as plain:
        settings(at(live, "tls_mode=disable")).connect()
    assert plain.value.sqlstate == "28000"
    trusted = ended(settings(at(live, "tls_mode=disable", password=False)).connect())
    assert isinstance(trusted.target, Tcp)
    assert isinstance(
        ended(settings(at(live, "tls_mode=require")).connect()).target, Tls
    )
    roots = quote(live.ca, safe="")
    ended(
        settings(
            at(live, f"tls_mode=verify-ca&tls_roots={roots}&server_name=else")
        ).connect()
    )
    ended(
        settings(
            at(live, f"tls_mode=verify-full&tls_roots={roots}&server_name=localhost")
        ).connect()
    )
    with pytest.raises(OperationalError, match="handshake"):
        settings(
            at(live, f"tls_mode=verify-full&tls_roots={roots}&server_name=else")
        ).connect()
    stranger = quote(live.stranger, safe="")
    with pytest.raises(OperationalError, match="handshake"):
        settings(at(live, f"tls_mode=verify-ca&tls_roots={stranger}")).connect()


def test_a_local_socket_takes_no_tls(live: Live) -> None:
    """Verifies: [CLIENT TLS by mode] no TLS over a Unix socket or a named pipe.

    Whatever the mode; `channel_binding` `require` refused before the
    login, of settings that cannot bind (28000); `disable` and `prefer`
    log in.
    """
    path = quote(live.socket, safe="")
    secret = quote(live.password, safe="")
    local = ended(
        settings(f"turborel://ANN:{secret}@{path}/?tls_mode=require").connect()
    )
    assert isinstance(local.target, Local)
    with pytest.raises(OperationalError) as unbound:
        settings(f"turborel://ANN:{secret}@{path}/?channel_binding=require").connect()
    assert unbound.value.sqlstate == "28000"
    ended(settings(at(live, "channel_binding=disable")).connect())
    ended(settings(at(live, "channel_binding=require")).connect())


def test_passwords_and_services_from_their_files(live: Live, tmp_path: Path) -> None:
    """Verifies: [CLIENT The password file] a password looked up by server and user.

    [CLIENT The service file] a service's section; [CLIENT Where settings
    come from] named by the environment, read through a function.
    """
    passfile = tmp_path / "pass"
    escaped = live.password.replace("\\", "\\\\").replace(":", "\\:")
    passfile.write_text(f"{live.host}:{live.port}:ANN:{escaped}\n")
    services = tmp_path / "services.conf"
    services.write_text(
        f"[ledger]\nhost = {live.host}\nport = {live.port}\nuser = ANN\n"
    )
    environment = {
        "TURBOREL_SERVICE": "ledger",
        "TURBOREL_SERVICE_FILE": str(services),
        "TURBOREL_PASSFILE": str(passfile),
    }
    made = Settings.resolve_in(Options(), environment.get)
    assert made.password_for(Tcp(live.host, live.port)) == live.password
    ended(made.connect())


def test_several_servers(live: Live) -> None:
    """Verifies: [CLIENT Several servers] hosts in order, one unreachable passed.

    Each address a name resolves to tried; with none kept, each and why
    (08001), 28000 if the last refused the user; in a random order with
    `load_balance=random`.
    """
    secret = quote(live.password, safe="")
    hosts = f"127.0.0.1:1,{live.host}:{live.port}"
    ended(settings(f"turborel://ANN:{secret}@{hosts}/?connect_timeout=5").connect())
    ended(settings(f"turborel://ANN:{secret}@{hosts}/?load_balance=random").connect())
    ended(settings(f"turborel://ANN:{secret}@localhost:{live.port}/").connect())
    with pytest.raises(OperationalError) as none:
        settings("turborel://ANN@127.0.0.1:1,127.0.0.1:2/?connect_timeout=5").connect()
    assert none.value.sqlstate == "08001"
    assert "127.0.0.1 (127.0.0.1:1)" in none.value.message
    assert "127.0.0.1 (127.0.0.1:2)" in none.value.message
    wrong = f"turborel://ANN:wrong@127.0.0.1:1,{live.host}:{live.port}/"
    with pytest.raises(OperationalError) as refused:
        settings(wrong).connect()
    assert refused.value.sqlstate == "28000"
    with pytest.raises(OperationalError) as unresolved:
        settings("turborel://ANN@no-such-host.invalid/").connect()
    assert unresolved.value.sqlstate == "08006"


def test_a_server_of_the_role_asked(live: Live) -> None:
    """Verifies: [CLIENT Several servers] `target=read-write`; `read-only`.

    The role told by SERVER_READ_ONLY; of a server that does not tell
    it, read from INFORMATION_SCHEMA.REPLICAS; the role a connection's
    session sees.
    """
    ended(settings(at(live, "target=read-write")).connect())
    with pytest.raises(OperationalError) as replica:
        settings(at(live, "target=read-only")).connect()
    assert replica.value.sqlstate == "08001"
    assert replica.value.message == "the server is read-write, and read-only is asked"
    told = connect_local(live.socket, "ANN", Trust())
    assert role(told) is Role.READ_WRITE
    told.terminate()
    untold = connect_to(Local(live.socket), "ANN", Trust(), offer=Offer.none())
    assert untold.setting("SERVER_READ_ONLY") is None
    assert role(untold) is Role.READ_WRITE
    assert not untold.in_transaction
    untold.terminate()


def test_a_client_certificate_named_by_settings(live: Live) -> None:
    """Verifies: [CLIENT Connecting by settings] with no password, a certificate.

    Presented with its key, and the server proves the user its common
    name names; one named without its key refused.
    """
    chain, key = (
        quote(live.client_certificate, safe=""),
        quote(live.client_key, safe=""),
    )
    base = at(live, f"tls_mode=require&tls_certificate={chain}", password=False)
    proved = settings(f"{base}&tls_key={key}").connect()
    assert proved.authorization == "ANN"
    ended(proved)
    with pytest.raises(
        OperationalError, match="presented with its key, and none is named"
    ):
        settings(base).connect()
