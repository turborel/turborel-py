"""Connecting as settings say, to one of several servers [CLIENT Several servers].

Each host is tried in the order given, or in an order drawn at random
for each connection with `load_balance=random`, and each address a
host's name resolves to in turn, every step within the connect timeout.
A server reached, logged in to and of the role the settings ask is
kept; another is left and the next tried. With none kept, the failure
says why each was not. [CLIENT TLS by mode] says how each uses TLS.
"""

from __future__ import annotations

import secrets
import socket
import ssl
from enum import Enum
from typing import TYPE_CHECKING, Final, TypeVar

from turborel._auth.mechanisms import (
    Certificate,
    ChannelBinding,
    Mechanism,
    Scram,
    Trust,
)
from turborel._client.connect import in_the_clear, logged_in
from turborel._errors import (
    CONNECTION_FAILURE_SQLCODE,
    Error,
    OperationalError,
    connection_failure,
)
from turborel._session.capabilities import APPLICATION, Offer
from turborel._settings.options import invalid
from turborel._settings.values import LoadBalance, TargetRole, TlsMode
from turborel._tls.contexts import channel, present, roots, secure
from turborel._transport.stream import Stream
from turborel._transport.target import Local, Tcp, Tls, open_target, tcp_to
from turborel._transport.timeouts import Timeouts, io_failed

if TYPE_CHECKING:
    from turborel._auth.mechanisms import TlsChannel
    from turborel._client.connection import Connection
    from turborel._settings.settings import Host, Settings, TlsFiles
    from turborel._transport.target import Target

MULTIPLIER: Final = 6_364_136_223_846_793_005
"""The multiplier of the generator that orders hosts at random (Knuth's MMIX)."""
INCREMENT: Final = 1_442_695_040_888_963_407
"""Its increment (MMIX's)."""
DRAW_SHIFT: Final = 33
"""The high bits of its state taken for each draw, the low ones being weakest."""
_U64: Final = (1 << 64) - 1
INVALID_AUTHORIZATION: Final = "28000"
"""SQLSTATE 28000: credentials refused, or a channel binding that cannot be made."""
ROLE_QUERY: Final = "SELECT ROLE FROM INFORMATION_SCHEMA.REPLICAS WHERE IS_SELF = 'YES'"
"""The query of a server's own role in its group."""
SERVER_READ_ONLY: Final = "SERVER_READ_ONLY"
"""The session status of whether the server takes no changes."""
_NO_SUCH_TABLE_CLASSES: Final = ("2A", "42")

_T = TypeVar("_T")


def shuffle(items: list[_T], seed: int) -> None:
    """`items` in an order drawn from `seed`, Fisher and Yates's way."""
    state = seed & _U64
    for i in range(len(items) - 1, 0, -1):
        state = (state * MULTIPLIER + INCREMENT) & _U64
        drawn = (state >> DRAW_SHIFT) % (i + 1)
        items[i], items[drawn] = items[drawn], items[i]


def seed() -> int:
    """A seed of the system's randomness."""
    return secrets.randbits(64)


class Role(Enum):
    """What a server is, to a connection's session."""

    READ_WRITE = "read-write"
    READ_ONLY = "read-only"
    UNKNOWN = "of a role this session cannot see"
    """A replica whose role the session cannot see."""


def role_of(rows: list[tuple[object, ...]] | None, failure: Error | None) -> Role:
    """The role the answer to `ROLE_QUERY` shows: its rows, or its failure.

    Raises:
        Error: Its failure, unless of a server alone, which has no REPLICAS.
    """
    if failure is not None:
        if failure.sqlstate.startswith(_NO_SUCH_TABLE_CLASSES):
            return Role.READ_WRITE
        raise failure
    if not rows:
        return Role.UNKNOWN
    shown = rows[0][0] if rows[0] else None
    return Role.READ_WRITE if str(shown).rstrip() == "PRIMARY" else Role.READ_ONLY


def role(connection: Connection) -> Role:
    """The role of `connection`'s server, as its session sees it.

    As SERVER_READ_ONLY last told it; else asked by a statement that is
    its own transaction, so it leaves none open.

    Raises:
        Error: The connection's; the query's, but of a server alone.
    """
    told = connection.setting(SERVER_READ_ONLY)
    if told is not None:
        return Role.READ_ONLY if told == "YES" else Role.READ_WRITE
    autocommit = connection.autocommit
    connection.autocommit = True
    try:
        outcome = connection.query(ROLE_QUERY)
    except Error as e:
        return role_of(None, e)
    finally:
        connection.autocommit = autocommit
    return role_of(getattr(outcome, "rows", []), None)


def context(mode: TlsMode, tls: TlsFiles) -> ssl.SSLContext | None:
    """The client's TLS of `mode`, of what `tls` names; none of `disable`.

    `prefer` and `require` check that the server holds the key of the
    certificate it presents but not who signed it; `verify-ca` checks it
    against the authorities trusted, not its name; `verify-full` both.

    Raises:
        OperationalError: SQLSTATE 08006, if a file cannot be read, a
            certificate is named without its key, or `verify-ca` or
            `verify-full` is asked with no authority trusted.
    """
    if mode is TlsMode.DISABLE:
        return None
    if mode.verifies():
        made = roots(tls.roots, platform=tls.system_roots)
        made.check_hostname = mode is TlsMode.VERIFY_FULL
    else:
        made = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        made.minimum_version = ssl.TLSVersion.TLSv1_2
        made.check_hostname = False
        made.verify_mode = ssl.CERT_NONE
    if tls.certificate is not None:
        if tls.key is None:
            msg = "a client certificate is presented with its key, and none is named"
            raise connection_failure(msg)
        present(made, tls.certificate, tls.key)
    return made


def targets_of(
    host: Host, server_name: str | None, tls: ssl.SSLContext | None
) -> list[tuple[str, Target | Error]]:
    """The targets of `host`, named: its local socket, or each address of its name."""
    if isinstance(host, Local):
        return [(host.path, host)]
    try:
        found = socket.getaddrinfo(host.host, host.port, type=socket.SOCK_STREAM)
    except OSError as e:
        return [(f"{host.host}:{host.port}", io_failed("resolve the name", e))]
    named: list[tuple[str, Target | Error]] = []
    for _, _, _, _, address in found:
        ip = str(address[0])
        shown = f"[{ip}]:{host.port}" if ":" in ip else f"{ip}:{host.port}"
        at = f"{host.host} ({shown})"
        target: Target = (
            Tcp(ip, host.port)
            if tls is None
            else Tls(ip, tls, host.port, server_name or host.host)
        )
        named.append((at, target))
    return named


def mechanism_of(settings: Settings, host: Host, target: Target) -> Mechanism:
    password = settings.password_for(host)
    mechanism: Mechanism
    if password is not None:
        mechanism = Scram(
            password, channel_binding=settings.channel_binding, cache=settings.key_cache
        )
    elif settings.tls.certificate is not None:
        mechanism = Certificate()
    else:
        mechanism = Trust()
    binds = isinstance(mechanism, Scram) and isinstance(target, Tls)
    if settings.channel_binding is ChannelBinding.REQUIRE and not binds:
        msg = "channel binding is required: SCRAM over TLS alone binds one"
        raise OperationalError(
            msg, sqlcode=CONNECTION_FAILURE_SQLCODE, sqlstate=INVALID_AUTHORIZATION
        )
    return mechanism


def _opened(
    settings: Settings, target: Target, within: float | None
) -> tuple[Target, Stream, TlsChannel | None]:
    """The stream to `target`; under `prefer`, over plain TCP if TLS cannot be begun."""
    if settings.tls_mode is TlsMode.PREFER and isinstance(target, Tls):
        tcp = tcp_to(target.host, target.port, within)
        try:
            secured = secure(tcp, target.server_name or target.host, target.context)
        except OperationalError:
            plain = Tcp(target.host, target.port)
            stream, _ = open_target(plain, within)
            return plain, stream, None
        return target, Stream(secured.socket), channel(secured.socket)
    stream, bound = open_target(target, within)
    return target, stream, bound


def _attempt(settings: Settings, host: Host, target: Target) -> Connection:
    timeouts = Timeouts(connect=settings.connect_timeout, read=None)
    target, stream, bound = _opened(settings, target, timeouts.connect)
    try:
        mechanism = mechanism_of(settings, host, target)
        if isinstance(target, Tcp):
            in_the_clear(mechanism)
    except Error:
        stream.close()
        raise
    offer = Offer()
    if settings.application_name is not None:
        offer = offer.attribute(APPLICATION, settings.application_name)
    connection = logged_in(
        target, (stream, bound), (settings.user, mechanism), timeouts, offer
    )
    _of_role(settings, connection)
    return connection


def _of_role(settings: Settings, connection: Connection) -> None:
    """Refuse `connection`, ended, if its server is not of the role asked (08001)."""
    if settings.target is TargetRole.ANY:
        return
    wanted = (
        Role.READ_WRITE if settings.target is TargetRole.READ_WRITE else Role.READ_ONLY
    )
    try:
        found = role(connection)
    except Error:
        connection.close()
        raise
    if found is not wanted:
        connection.close()
        msg = f"the server is {found.value}, and {wanted.value} is asked"
        raise invalid(msg)


def none_kept(tried: list[tuple[str, Error]]) -> Error:
    """The failure of a connection none of `tried` gave."""
    if len(tried) == 1:
        return tried[0][1]
    refused = bool(tried) and tried[-1][1].sqlstate.startswith("28")
    reasons = "; ".join(f"{at}: {e.message}" for at, e in tried)
    message = f"no server was kept: {reasons}" if tried else "no server is named"
    state = INVALID_AUTHORIZATION if refused else "08001"
    return OperationalError(message, sqlcode=CONNECTION_FAILURE_SQLCODE, sqlstate=state)


def connect(settings: Settings) -> Connection:
    """A connection to the first server the settings let keep.

    Raises:
        Error: As `Settings.connect` raises.
    """
    hosts = list(settings.hosts)
    if settings.load_balance is LoadBalance.RANDOM:
        shuffle(hosts, seed())
    tls = context(settings.tls_mode, settings.tls)
    tried: list[tuple[str, Error]] = []
    for host in hosts:
        tls_here = None if isinstance(host, Local) else tls
        for at, target in targets_of(host, settings.tls.server_name, tls_here):
            if isinstance(target, Error):
                tried.append((at, target))
                continue
            try:
                return _attempt(settings, host, target)
            except Error as e:
                tried.append((at, e))
    raise none_kept(tried)
