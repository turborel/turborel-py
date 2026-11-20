"""Tests of connection settings, as turborel-client's own settings tests read them.

The URI, the service file, the password file, the environment, and the
order the layers are laid in; each case one of `client/src/settings/
tests.rs` at 1c4187e4.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from turborel import OperationalError
from turborel._settings import files
from turborel.client import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    ENVIRONMENT,
    LoadBalance,
    Local,
    Options,
    Settings,
    TargetRole,
    Tcp,
    TlsMode,
)
from turborel.client import ChannelBinding as Binding

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def environment(pairs: dict[str, str]) -> Callable[[str], str | None]:
    """An environment of `pairs`, as `Settings.resolve_in` reads one."""
    return pairs.get


def test_a_uri_gives_its_user_hosts_and_settings() -> None:
    """Verifies: [CLIENT The connection URI] user, password, hosts and ports, settings.

    Its parts percent-encoded, an IPv6 address in brackets, a Unix
    socket's path; the password never shown; a URI of no host, localhost.
    """
    uri = (
        "turborel://ann:p%40ss@db1:7000,[::1]:7001,db3,%2Frun%2Fs.sock/"
        "?tls_mode=verify-full&target=read-write&connect_timeout=5"
    )
    options = Options.from_uri(uri)
    assert (options.get("user"), options.get("password")) == ("ann", "p@ss")
    settings = Settings.resolve_in(options, environment({}))
    assert settings.hosts == (
        Tcp("db1", 7000),
        Tcp("::1", 7001),
        Tcp("db3", DEFAULT_PORT),
        Local("/run/s.sock"),
    )
    assert (settings.tls_mode, settings.target) == (
        TlsMode.VERIFY_FULL,
        TargetRole.READ_WRITE,
    )
    assert settings.connect_timeout == 5.0
    assert "p@ss" not in f"{options!r} {settings!r}"
    bare = Settings.resolve_in(Options.from_uri("turborel://ann@/"), environment({}))
    assert bare.hosts == (Tcp(DEFAULT_HOST, DEFAULT_PORT),)


@pytest.mark.parametrize(
    "uri",
    [
        "other://a@b",
        "turborel://a@b/db",
        "turborel://a@b/?colour=red",
        "turborel://a@b/?tls_mode",
        "turborel://a%4@b",
        "turborel://a%ff@b",
    ],
)
def test_a_malformed_uri_is_refused(uri: str) -> None:
    """Verifies: [CLIENT The connection URI] another scheme, a path, an unknown setting.

    Or a pair without `=`, or bad percent-encoding, refused (08001).
    """
    with pytest.raises(OperationalError) as refused:
        Options.from_uri(uri)
    assert refused.value.sqlstate == "08001"


@pytest.mark.parametrize(
    "uri",
    [
        "turborel://a@b/?tls_mode=always",
        "turborel://a@b:port",
        "turborel://a@b/?connect_timeout=-1",
        "turborel://b",
    ],
)
def test_a_malformed_setting_is_refused(uri: str) -> None:
    """Verifies: [CLIENT Where settings come from] unreadable, 08001.

    A word no setting takes, a port that is no number, no user.
    """
    with pytest.raises(OperationalError) as refused:
        Settings.resolve_in(Options.from_uri(uri), environment({}))
    assert refused.value.sqlstate == "08001"


def test_settings_are_laid_program_service_environment_default(tmp_path: Path) -> None:
    """Verifies: [CLIENT Where settings come from] layers, in order.

    Then the defaults; the environment names the service and its file
    where the program does not; an empty variable gives nothing.
    """
    file = tmp_path / "services.conf"
    file.write_text(
        "# servers\n[prod]\nhost = prod-db\nport = 7500\ntls_mode = require\n\n"
        "[test]\nhost = test-db\n"
    )
    env = environment(
        {
            "TURBOREL_SERVICE": "prod",
            "TURBOREL_SERVICE_FILE": str(file),
            "TURBOREL_USER": "env-user",
            "TURBOREL_PORT": "7600",
            "TURBOREL_TLS_MODE": "disable",
            "TURBOREL_APPLICATION_NAME": "",
        }
    )
    explicit = Options().set("tls_mode", "verify-ca")
    settings = Settings.resolve_in(explicit, env)
    assert settings.hosts == (Tcp("prod-db", 7500),)
    assert settings.tls_mode is TlsMode.VERIFY_CA
    assert settings.user == "env-user"
    assert settings.application_name is None
    assert settings.channel_binding is Binding.PREFER
    explicit.set("service", "test")
    assert Settings.resolve_in(explicit, env).hosts == (Tcp("test-db", 7600),)


def test_a_service_file_is_read_by_section() -> None:
    """Verifies: [CLIENT The service file] sections, `setting = value` lines, comments.

    A section not there, a setting before any section, a line without
    `=`, a key no setting has, and a service or service file set by a
    service refused, the line named.
    """
    options = files.service(
        "[a]\nuser=ann\n[b]\nuser = bob\n  host =  h  \n", "b", "s.conf"
    )
    assert (options.get("user"), options.get("host")) == ("bob", "h")
    with pytest.raises(OperationalError, match="has no service b"):
        files.service("[a]\nuser=ann\n", "b", "s.conf")
    for text, why in [
        ("user=ann\n", "line 1: a setting comes before any section"),
        ("[a]\nuser\n", "line 2: a setting is <key> = <value>"),
        ("[a]\ncolour=red\n", "line 2: colour is no connection setting"),
        ("[a]\nservice=b\n", "line 2: a service cannot set service"),
        ("[a\n", "line 1: a section's name ends with ]"),
    ]:
        with pytest.raises(
            OperationalError, match=why.replace("]", "\\]").replace("[", "\\[")
        ):
            files.service(text, "a", "s.conf")


def test_a_password_file_matches_by_host_port_and_user(tmp_path: Path) -> None:
    r"""Verifies: [CLIENT The password file] `host:port:user:password`, `*`, `\`, `#`.

    The first line matching host, port and user taken, an escaped `\*`
    matching only `*`; the settings' own password over it; a file that
    cannot be read gives none.
    """
    text = (
        "# passwords\nshort:line\ndb1:7422:ann:first\n*:*:ann:any\\:host\n"
        "db\\:2:*:bob:c:\\\\d\n\\*:1:carl:star\n"
    )
    assert files.password(text, ("db1", "7422", "ann")) == "first"
    assert files.password(text, ("db9", "1", "ann")) == "any:host"
    assert files.password(text, ("db:2", "7", "bob")) == "c:\\d"
    assert files.password(text, ("x", "1", "carl")) is None
    assert files.password(text, ("*", "1", "carl")) == "star"
    assert files.password(text, ("db1", "7422", "nobody")) is None
    passfile = tmp_path / "pass"
    passfile.write_text(text)
    explicit = (
        Options().set("user", "ann").set("passfile", str(passfile)).set("host", "db1")
    )
    settings = Settings.resolve_in(explicit, environment({}))
    assert settings.password_for(Tcp("db1", 7422)) == "first"
    explicit.set("password", "given")
    assert (
        Settings.resolve_in(explicit, environment({})).password_for(Tcp("db1", 7422))
        == "given"
    )
    passfile.unlink()
    assert settings.password_for(Tcp("db1", 7422)) is None


def test_the_environment_and_words_are_read() -> None:
    """Verifies: [CLIENT Where settings come from] each variable, each word.

    The defaults of each, hosts each of the port at its place.
    """
    options = Options.environment(environment({name: "v" for name, _ in ENVIRONMENT}))
    assert all(options.get(key) == "v" for _, key in ENVIRONMENT)
    explicit = Options(
        {"user": "u", "host": "a,b", "port": "1,2", "tls_system_roots": "true"}
    )
    explicit.set("channel_binding", "require").set("load_balance", "random")
    settings = Settings.resolve_in(explicit, environment({}))
    assert settings.hosts == (Tcp("a", 1), Tcp("b", 2))
    assert settings.tls.system_roots
    assert (settings.channel_binding, settings.load_balance) == (
        Binding.REQUIRE,
        LoadBalance.RANDOM,
    )
    assert TlsMode.VERIFY_CA.verifies()
    assert not TlsMode.REQUIRE.verifies()
    with pytest.raises(OperationalError, match="any, read-write, read-only"):
        Settings.resolve_in(
            Options({"user": "u", "target": "primary"}), environment({})
        )
    defaults = Settings.resolve_in(Options({"user": "u"}), environment({}))
    assert (defaults.tls_mode, defaults.target, defaults.connect_timeout) == (
        TlsMode.PREFER,
        TargetRole.ANY,
        30.0,
    )
    none_at_all = Settings.resolve_in(
        Options({"user": "u", "connect_timeout": "0"}), environment({})
    )
    assert none_at_all.connect_timeout is None


def refused(pairs: dict[str, str]) -> tuple[object, ...] | str:
    """The hosts settings of `pairs` give, or the SQLSTATE of their refusal."""
    try:
        return Settings.resolve_in(
            Options({"user": "u", **pairs}), environment({})
        ).hosts
    except OperationalError as e:
        return e.sqlstate


def test_malformed_hosts_and_words_are_refused(tmp_path: Path) -> None:
    """Verifies: [CLIENT Where settings come from] malformed hosts.

    An IPv6 port that is no number, a port of the list that is none, a
    word no setting takes, refused (08001); several hosts of one port
    each take it; a service file that cannot be read refused.
    """
    for host in ("a,,b", "[::1", "[::1]:x"):
        assert refused({"host": host}) == "08001", host
    assert refused({"host": "a", "port": "1,x"}) == "08001"
    for key in ("channel_binding", "target", "load_balance", "tls_system_roots"):
        assert refused({key: "sometimes"}) == "08001", key
    assert refused({"host": "a,b,[::1]", "port": "9"}) == (
        Tcp("a", 9),
        Tcp("b", 9),
        Tcp("::1", 9),
    )
    assert refused({"host": "fe80::1"}) == (Tcp("fe80::1", DEFAULT_PORT),)
    with pytest.raises(OperationalError) as unread:
        files.read_service(str(tmp_path / "none"), "s")
    assert unread.value.sqlstate == "08001"
    missing = Options(
        {"user": "u", "service": "s", "service_file": str(tmp_path / "none")}
    )
    with pytest.raises(OperationalError):
        Settings.resolve_in(missing, environment({}))


def test_a_password_file_matches_a_local_socket_by_its_path(tmp_path: Path) -> None:
    """Verifies: [CLIENT The password file] a socket by its path and 7422.

    Read only if a regular file, or a link to one: a directory gives none.
    """
    passfile = tmp_path / "pass"
    passfile.write_text(f"/run/s.sock:{DEFAULT_PORT}:ann:local\n")
    settings = Settings.resolve_in(
        Options({"user": "ann", "passfile": str(passfile)}), environment({})
    )
    assert settings.password_for(Local("/run/s.sock")) == "local"
    directory = Settings.resolve_in(
        Options({"user": "ann", "passfile": str(tmp_path)}), environment({})
    )
    assert directory.password_for(Local("/run/s.sock")) is None
    assert files.read_regular(str(tmp_path / "none")) is None
