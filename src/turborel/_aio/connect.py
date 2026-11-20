"""Connecting for asyncio, as settings say [CLIENT Connecting by settings].

As `_settings/failover.py` connects, each step awaited: each host in
order or at random, each address of its name, TLS by mode, `prefer`
connecting again without TLS after a failed handshake, the user proved
as the settings say, and the server kept only if of the role asked.
"""

from __future__ import annotations

import asyncio
import socket
import sys
from typing import TYPE_CHECKING

from turborel._aio.client import AsyncClient
from turborel._aio.streams import AsyncStream
from turborel._client.connect import in_the_clear
from turborel._errors import Error, OperationalError, connection_failure
from turborel._session.capabilities import APPLICATION, Offer
from turborel._settings import failover
from turborel._settings.options import invalid
from turborel._settings.values import LoadBalance, TargetRole, TlsMode
from turborel._tls.contexts import channel
from turborel._transport.pipe import open_pipe
from turborel._transport.stream import Stream
from turborel._transport.target import Local, Tcp, Tls
from turborel._transport.timeouts import Timeouts, io_failed

if TYPE_CHECKING:
    import ssl

    from turborel._auth.mechanisms import TlsChannel
    from turborel._settings.settings import Host, Settings
    from turborel._transport.target import Target


async def _tcp(
    target: Tcp | Tls, within: float | None, tls: ssl.SSLContext | None
) -> AsyncStream:
    try:
        opening = asyncio.open_connection(target.host, target.port)
        reader, writer = await asyncio.wait_for(opening, within)
    except (OSError, TimeoutError) as e:
        raise io_failed("connect", e) from e
    sock = writer.get_extra_info("socket")
    if sock is not None:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    if tls is not None:
        assert isinstance(target, Tls)  # noqa: S101  # Of a context, a TLS target.
        name = target.server_name or target.host
        try:
            await asyncio.wait_for(writer.start_tls(tls, server_hostname=name), within)
        except (OSError, TimeoutError, ValueError) as e:
            writer.close()
            msg = f"the TLS handshake failed: {e}"
            raise connection_failure(msg) from e
    return AsyncStream(reader, writer)


async def _local(path: str, within: float | None) -> AsyncStream:
    if sys.platform == "win32":
        held = await asyncio.to_thread(open_pipe, path, within)
        local = AsyncStream(None, None, Stream(held))
    else:
        local = await _unix(path, within)
    return local


async def _unix(path: str, within: float | None) -> AsyncStream:
    # Not on Windows, whose local transport is a named pipe.
    opening = getattr(asyncio, "open_unix_connection")  # noqa: B009
    try:
        reader, writer = await asyncio.wait_for(opening(path), within)
    except (OSError, TimeoutError) as e:
        raise io_failed("connect", e) from e
    return AsyncStream(reader, writer)


def _channel(stream: AsyncStream) -> TlsChannel | None:
    writer = stream.writer
    secured = None if writer is None else writer.get_extra_info("ssl_object")
    return None if secured is None else channel(secured)


async def open_target(target: Target, within: float | None) -> AsyncStream:
    """The stream to `target`.

    Raises:
        OperationalError: SQLSTATE 08006, if it cannot be reached or its TLS
            handshake fails.
    """
    if isinstance(target, Local):
        return await _local(target.path, within)
    return await _tcp(
        target, within, target.context if isinstance(target, Tls) else None
    )


async def logged_in(
    target: Target,
    stream: AsyncStream,
    who: tuple[str, object],
    within: Timeouts,
    offer: Offer,
) -> AsyncClient:
    """A connection over `stream` to `target`, `who` logged in.

    Raises:
        Error: As the server refuses the login, or the connection fails.
    """
    user, mechanism = who
    bound = _channel(stream)
    if bound is not None:
        mechanism.bind(bound)  # type: ignore[attr-defined]  # A mechanism.
    stream.set_timeout(within.connect)
    client = AsyncClient(stream, target)
    await client.log_in(user, mechanism, offer)  # type: ignore[arg-type]
    client.set_read_timeout(within.read)
    return client


async def _opened(
    settings: Settings, target: Target, within: float | None
) -> tuple[Target, AsyncStream]:
    if settings.tls_mode is TlsMode.PREFER and isinstance(target, Tls):
        try:
            return target, await open_target(target, within)
        except OperationalError as e:
            if "handshake" not in e.message:
                raise
            plain = Tcp(target.host, target.port)
            return plain, await open_target(plain, within)
    return target, await open_target(target, within)


async def _role(client: AsyncClient) -> failover.Role:
    told = client.setting(failover.SERVER_READ_ONLY)
    if told is not None:
        return failover.Role.READ_ONLY if told == "YES" else failover.Role.READ_WRITE
    autocommit = client.autocommit
    client.autocommit = True
    try:
        outcome = await client.query(failover.ROLE_QUERY)
    except Error as e:
        return failover.role_of(None, e)
    finally:
        client.autocommit = autocommit
    return failover.role_of(getattr(outcome, "rows", []), None)


async def _attempt(settings: Settings, host: Host, target: Target) -> AsyncClient:
    timeouts = Timeouts(connect=settings.connect_timeout, read=None)
    target, stream = await _opened(settings, target, timeouts.connect)
    try:
        mechanism = failover.mechanism_of(settings, host, target)
        if isinstance(target, Tcp):
            in_the_clear(mechanism)
    except Error:
        stream.close()
        raise
    offer = Offer()
    if settings.application_name is not None:
        offer = offer.attribute(APPLICATION, settings.application_name)
    client = await logged_in(
        target, stream, (settings.user, mechanism), timeouts, offer
    )
    if settings.target is not TargetRole.ANY:
        wanted = (
            failover.Role.READ_WRITE
            if settings.target is TargetRole.READ_WRITE
            else failover.Role.READ_ONLY
        )
        try:
            found = await _role(client)
        except Error:
            client.close()
            raise
        if found is not wanted:
            client.close()
            msg = f"the server is {found.value}, and {wanted.value} is asked"
            raise invalid(msg)
    return client


async def connect(settings: Settings) -> AsyncClient:
    """A connection to the first server the settings let keep.

    Raises:
        Error: As `Settings.connect` raises.
    """
    hosts = list(settings.hosts)
    if settings.load_balance is LoadBalance.RANDOM:
        failover.shuffle(hosts, failover.seed())
    tls = failover.context(settings.tls_mode, settings.tls)
    tried: list[tuple[str, Error]] = []
    for host in hosts:
        here = None if isinstance(host, Local) else tls
        targets = await asyncio.to_thread(
            failover.targets_of,
            host,
            settings.tls.server_name,
            here,
        )
        for at, target in targets:
            if isinstance(target, Error):
                tried.append((at, target))
                continue
            try:
                return await _attempt(settings, host, target)
            except Error as e:
                tried.append((at, e))
    raise failover.none_kept(tried)
