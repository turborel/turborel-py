"""Connection settings: how to connect, as the layers of options say.

[CLIENT Connecting by settings] [CLIENT Where settings come from]. The
program's own options, or a URI's, then a service's section of the
service file, then the environment, then the defaults, each setting
taken from the first layer that has it. A password none of them gives
is looked up in the password file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final, TypeVar

from turborel._auth.cache import KeyCache
from turborel._auth.mechanisms import ChannelBinding
from turborel._settings import files, values
from turborel._settings.options import (
    APPLICATION_NAME,
    CHANNEL_BINDING,
    CONNECT_TIMEOUT,
    HOST,
    LOAD_BALANCE,
    PASSFILE,
    PASSWORD,
    PORT,
    SERVER_NAME,
    SERVICE,
    SERVICE_FILE,
    TARGET,
    TLS_CERTIFICATE,
    TLS_KEY,
    TLS_MODE,
    TLS_ROOTS,
    TLS_SYSTEM_ROOTS,
    USER,
    Options,
    invalid,
)
from turborel._settings.uri import from_uri
from turborel._settings.values import LoadBalance, TargetRole, TlsMode
from turborel._transport.target import DEFAULT_PORT, Local, Tcp
from turborel._transport.timeouts import CONNECT_WITHIN

if TYPE_CHECKING:
    from collections.abc import Callable

    from turborel._client.connection import Connection

DEFAULT_HOST: Final = "localhost"
"""The host connected to when none is named."""
DEFAULT_SERVICE_FILE: Final = ".turborel_service.conf"
"""The service file read when none is named, in the home directory."""
DEFAULT_PASSFILE: Final = ".turborel_pass"
"""The password file read when none is named, in the home directory."""
_LIST: Final = ","
_CONNECT_DEFAULT: Final[float | None] = CONNECT_WITHIN

Host = Tcp | Local
"""Where a server is: a host and port over TCP, or a local socket or named pipe."""

_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class TlsFiles:
    """The files a connection's TLS is made of, and the name its server goes by."""

    roots: str | None = None
    """A PEM file of the authorities trusted."""
    system_roots: bool = False
    """Whether the platform's authorities are trusted too."""
    certificate: str | None = None
    """A PEM file of the client's certificate chain, to present."""
    key: str | None = None
    """A PEM file of its private key."""
    server_name: str | None = None
    """The name the server's certificate is checked against, if not the host's."""


def _port(key: str, text: str) -> int:
    stripped = text.strip()
    if not stripped.isdigit() or not stripped.isascii() or int(stripped) > 0xFFFF:  # noqa: PLR2004
        msg = f"{key} is {text}, no port"
        raise invalid(msg)
    return int(stripped)


def _hosts(hosts: str, ports: str) -> list[Host]:
    numbers = [_port(PORT, p) for p in ports.split(_LIST) if p.strip()]

    def fallback(i: int) -> int:
        if i < len(numbers):
            return numbers[i]
        return numbers[0] if len(numbers) == 1 else DEFAULT_PORT

    return [
        _host(name.strip(), fallback(i)) for i, name in enumerate(hosts.split(_LIST))
    ]


def _host(name: str, default: int) -> Host:
    """The host `name` is: a path, `[<IPv6>]`, `[<IPv6>]:<port>`, `<name>:<port>`."""
    if not name:
        msg = "a host of the list is empty"
        raise invalid(msg)
    if name.startswith(("/", "\\")):
        return Local(name)
    if name.startswith("["):
        address, closed, after = name[1:].partition("]")
        if not closed:
            msg = f"{name} has no ]"
            raise invalid(msg)
        port = _port(HOST, after[1:]) if after.startswith(":") else default
        return Tcp(address, port)
    host, colon, port_text = name.partition(":")
    # A name of two colons or more is an IPv6 address unbracketed, of no port.
    if colon and ":" not in port_text:
        return Tcp(host, _port(HOST, port_text))
    return Tcp(name, default)


def _seconds(key: str, text: str) -> float | None:
    stripped = text.strip()
    if not stripped.isdigit() or not stripped.isascii():
        msg = f"{key} is {text}, not a whole number of seconds"
        raise invalid(msg)
    n = int(stripped)
    return float(n) if n > 0 else None


def _at_home(name: str) -> str | None:
    home = Path("~").expanduser()
    return None if str(home) == "~" else str(home / name)


def _read(
    options: Options, key: str, parse: Callable[[str, str], _T], default: _T
) -> _T:
    text = options.get(key)
    return default if text is None else parse(key, text)


@dataclass(frozen=True, slots=True)
class Settings:
    """How to connect, as the settings say."""

    hosts: tuple[Host, ...]
    """The servers, tried in turn."""
    user: str
    password: str | None = field(default=None, repr=False)
    """The user's password, if given; else the password file's."""
    tls_mode: TlsMode = TlsMode.PREFER
    channel_binding: ChannelBinding = ChannelBinding.PREFER
    application_name: str | None = None
    """The program's name, as it tells the server."""
    connect_timeout: float | None = CONNECT_WITHIN
    """How long each step of connecting waits, in seconds; None, no limit."""
    passfile: str | None = None
    target: TargetRole = TargetRole.ANY
    load_balance: LoadBalance = LoadBalance.DISABLE
    tls: TlsFiles = field(default_factory=TlsFiles)
    key_cache: KeyCache = field(default_factory=KeyCache, repr=False, compare=False)
    """The SCRAM keys of its connections, so a reconnection skips their derivation."""

    @classmethod
    def resolve(cls, explicit: Options | None = None) -> Settings:
        """The settings `explicit` gives, a service's, the environment's, the default.

        Raises:
            OperationalError: SQLSTATE 08001, if a setting cannot be read, a
                service named cannot be read, or no user is named.
        """
        return cls.resolve_in(explicit or Options(), os.environ.get)

    @classmethod
    def from_uri(cls, uri: str) -> Settings:
        """The settings of the connection URI `uri`, laid as `resolve` lays them.

        Raises:
            OperationalError: SQLSTATE 08001, as `resolve` raises, or of a
                URI that is not one.
        """
        return cls.resolve(from_uri(uri))

    @classmethod
    def resolve_in(
        cls, explicit: Options, variable: Callable[[str], str | None]
    ) -> Settings:
        """The settings as `resolve` lays them, `variable` reading the environment.

        Raises:
            OperationalError: As `resolve` raises.
        """
        environment = Options.environment(variable)
        named = explicit.over(environment)
        service = Options()
        name = named.get(SERVICE)
        if name is not None:
            file = named.get(SERVICE_FILE) or _at_home(DEFAULT_SERVICE_FILE) or ""
            service = files.read_service(file, name)
        return cls._of(explicit.over(service).over(environment))

    @classmethod
    def _of(cls, options: Options) -> Settings:
        user = options.get(USER)
        if user is None:
            msg = "no user is named: by the program, a service, or TURBOREL_USER"
            raise invalid(msg)
        return cls(
            hosts=tuple(
                _hosts(options.get(HOST) or DEFAULT_HOST, options.get(PORT) or "")
            ),
            user=user,
            password=options.get(PASSWORD),
            tls_mode=_read(options, TLS_MODE, values.tls_mode, TlsMode.PREFER),
            channel_binding=_read(
                options, CHANNEL_BINDING, values.channel_binding, ChannelBinding.PREFER
            ),
            application_name=options.get(APPLICATION_NAME),
            connect_timeout=_read(options, CONNECT_TIMEOUT, _seconds, _CONNECT_DEFAULT),
            passfile=options.get(PASSFILE) or _at_home(DEFAULT_PASSFILE),
            target=_read(options, TARGET, values.target_role, TargetRole.ANY),
            load_balance=_read(
                options, LOAD_BALANCE, values.load_balance, LoadBalance.DISABLE
            ),
            tls=TlsFiles(
                roots=options.get(TLS_ROOTS),
                system_roots=_read(
                    options, TLS_SYSTEM_ROOTS, values.boolean, default=False
                ),
                certificate=options.get(TLS_CERTIFICATE),
                key=options.get(TLS_KEY),
                server_name=options.get(SERVER_NAME),
            ),
        )

    def password_for(self, host: Host) -> str | None:
        """The password to prove at `host`: the settings', else the password file's."""
        if self.password is not None:
            return self.password
        if self.passfile is None:
            return None
        text = files.read_regular(self.passfile)
        if text is None:
            return None
        if isinstance(host, Tcp):
            name, port = host.host, str(host.port)
        else:
            name, port = host.path, str(DEFAULT_PORT)
        return files.password(text, (name, port, self.user))

    def connect(self) -> Connection:
        """A connection to the first server reached, the user logged in, of the role.

        Raises:
            Error: The one server's failure, if there was one; else SQLSTATE
                08001, saying why each was not kept, or 28000 if the last
                refused the user; 28000 before any connection, of a channel
                binding required that cannot be made.
        """
        from turborel._settings.failover import connect  # noqa: PLC0415  # A cycle else.

        return connect(self)
