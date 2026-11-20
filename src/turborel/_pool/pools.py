"""A pool of connections: a bounded set a program's threads share [CLIENT Pools].

`get` hands out an idle connection that answers, or makes one while
fewer than `max` are made, or waits for one to come back, at most
`wait`. A connection handed out comes back as it is released, reset to
the state it logged in with; one lost, or whose reset fails, is closed
instead, so no borrower sees another's session. Idle beyond
`idle_timeout`, or older than `max_lifetime`, a connection is closed
rather than handed out, and no more than `max_idle` are kept idle. The
pool is thread-safe by the standard library's lock and condition alone,
and starts no thread, each wait being the waiting borrower's.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any, Final, Protocol, Self

from turborel._errors import (
    CONNECTION_FAILURE_SQLCODE,
    Error,
    OperationalError,
    connection_failure,
)
from turborel._pool import reset

if TYPE_CHECKING:
    from collections.abc import Callable
    from types import TracebackType

    from turborel._client.connection import Connection

DEFAULT_MAX: Final = 10
"""The connections a pool makes at most by default."""
DEFAULT_WAIT: Final = 30.0
"""How long `get` waits by default for a connection to come back, in seconds."""
DEFAULT_IDLE_TIMEOUT: Final = 600.0
"""How long a connection may stay idle by default: ten minutes."""
DEFAULT_MAX_LIFETIME: Final = 3600.0
"""How long a connection lives by default: an hour."""
UNABLE_TO_CONNECT: Final = "08001"
"""SQLSTATE 08001: no connection came back in time."""


class Source(Protocol):
    """What makes a pool's connections: settings, or any object of this method."""

    def connect(self) -> Connection:
        """A new connection, logged in."""
        ...


@dataclass(frozen=True, slots=True)
class PoolConfig:
    """How a pool keeps its connections; times in seconds, None for no limit."""

    max: int = DEFAULT_MAX
    """The most connections made at once, handed out and idle."""
    max_idle: int = DEFAULT_MAX
    """The most kept idle."""
    idle_timeout: float | None = DEFAULT_IDLE_TIMEOUT
    """How long one may stay idle; None, as long as it lives."""
    max_lifetime: float | None = DEFAULT_MAX_LIFETIME
    """How long one lives from when it was made; None, without limit."""
    wait: float = DEFAULT_WAIT
    """How long `get` waits for one to come back."""
    check: bool = True
    """Whether an idle connection is checked to answer before it is handed out."""
    reset: tuple[str, ...] = field(default_factory=tuple)
    """Statements run, after the pool's own, as each connection comes back."""


@dataclass(slots=True)
class _Idle:
    connection: Connection
    made: float
    since: float


class _Shared:
    def __init__(
        self, source: Source | Callable[[], Connection], config: PoolConfig
    ) -> None:
        self.source = source
        self.config = config
        self.idle: list[_Idle] = []
        self.made = 0
        self.lock = threading.Lock()
        self.returned = threading.Condition(self.lock)

    def make(self) -> Connection:
        connect = getattr(self.source, "connect", None)
        return connect() if callable(connect) else self.source()  # type: ignore[operator]  # A maker.

    def fresh(self, idle: _Idle, now: float) -> bool:
        lifetime, timeout = self.config.max_lifetime, self.config.idle_timeout
        lived = lifetime is None or now - idle.made < lifetime
        rested = timeout is None or now - idle.since < timeout
        return lived and rested and not idle.connection.is_lost

    def unmade(self) -> None:
        with self.lock:
            self.made = max(self.made - 1, 0)
            self.returned.notify()


class Pool:
    """A pool of connections; a copy of it, by `copy`, is the same pool."""

    def __init__(
        self,
        source: Source | Callable[[], Connection],
        config: PoolConfig | None = None,
    ) -> None:
        """A pool of connections `source` makes, kept as `config` says.

        `source` is settings, or anything of a `connect` method, or a
        function that makes a connection.
        """
        self._shared = _Shared(source, config or PoolConfig())

    def __copy__(self) -> Pool:
        """The same pool."""
        twin = Pool.__new__(Pool)
        twin._shared = self._shared  # noqa: SLF001  # Its kind's.
        return twin

    @property
    def config(self) -> PoolConfig:
        """How it keeps its connections."""
        return self._shared.config

    def get(self) -> Pooled:
        """A connection: idle and answering, else new, else the first back in time.

        Raises:
            OperationalError: SQLSTATE 08001, if none comes back within
                `wait`.
            Error: The source's failure to make one.
        """
        shared = self._shared
        deadline = time.monotonic() + shared.config.wait
        while True:
            idle, make = self._next(deadline)
            if idle is not None:
                pooled = self._checked(idle)
                if pooled is not None:
                    return pooled
                continue
            if make:
                try:
                    connection = shared.make()
                except Error:
                    shared.unmade()
                    raise
                return Pooled(connection, time.monotonic(), shared)
            msg = (
                f"no connection of the pool's {shared.config.max} came back"
                f" within {shared.config.wait} seconds"
            )
            raise OperationalError(
                msg, sqlcode=CONNECTION_FAILURE_SQLCODE, sqlstate=UNABLE_TO_CONNECT
            )

    def _next(self, deadline: float) -> tuple[_Idle | None, bool]:
        shared = self._shared
        with shared.lock:
            while True:
                now = time.monotonic()
                while shared.idle:
                    idle = shared.idle.pop()
                    if shared.fresh(idle, now):
                        return idle, False
                    shared.made = max(shared.made - 1, 0)
                    idle.connection.close()
                if shared.made < shared.config.max:
                    shared.made += 1
                    return None, True
                left = deadline - now
                if left <= 0:
                    return None, False
                shared.returned.wait(left)

    def _checked(self, idle: _Idle) -> Pooled | None:
        shared = self._shared
        if shared.config.check:
            try:
                reset.answers(idle.connection)
            except Error:
                idle.connection.close()
                shared.unmade()
                return None
        return Pooled(idle.connection, idle.made, shared)

    def close(self) -> None:
        """Close the idle connections; those handed out close as they are released.

        Python frees nothing on its own as a pool goes, so the program
        closes it, as a `with` block of it does.
        """
        shared = self._shared
        with shared.lock:
            idle, shared.idle = shared.idle, []
            shared.made = max(shared.made - len(idle), 0)
            shared.config = replace(shared.config, max_idle=0)
        for each in idle:
            each.connection.close()

    def __enter__(self) -> Self:
        """The pool."""
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the idle connections."""
        self.close()

    def counts(self) -> tuple[int, int]:
        """How many connections are made, handed out and idle, and how many are idle."""
        with self._shared.lock:
            return self._shared.made, len(self._shared.idle)


class Pooled:
    """A connection handed out by a pool, given back as it is released.

    It stands for its connection, every attribute of it read through;
    as a context manager it is released as the block ends.
    """

    def __init__(self, connection: Connection, made: float, shared: _Shared) -> None:
        """The connection `connection`, made at `made`, of the pool `shared`."""
        self._connection: Connection | None = connection
        self._made = made
        self._shared = shared

    def __enter__(self) -> Self:
        """The pooled connection."""
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Give the connection back."""
        self.release()

    def __getattr__(self, name: str) -> Any:  # noqa: ANN401  # Any of the connection's.
        """The connection's attribute `name`.

        Raises:
            OperationalError: SQLSTATE 08006, once it is given back.
        """
        return getattr(self.connection, name)

    def __setattr__(self, name: str, value: object) -> None:
        """Set the connection's attribute `name`; its own, of a name of `_`.

        Raises:
            OperationalError: SQLSTATE 08006, once it is given back.
        """
        if name.startswith("_"):
            object.__setattr__(self, name, value)
        else:
            setattr(self.connection, name, value)

    @property
    def connection(self) -> Connection:
        """The connection it stands for.

        Raises:
            OperationalError: SQLSTATE 08006, once it is given back.
        """
        if self._connection is None:
            msg = "the connection was given back to its pool"
            raise connection_failure(msg)
        return self._connection

    def release(self) -> None:
        """Give the connection back reset; else, as it says, close it."""
        connection, self._connection = self._connection, None
        if connection is None:
            return
        shared = self._shared
        lifetime = shared.config.max_lifetime
        lived = lifetime is not None and time.monotonic() - self._made >= lifetime
        kept = False
        if not lived:
            try:
                reset.reset(connection, shared.config.reset)
                kept = True
            except Error:
                kept = False
        with shared.lock:
            if kept and len(shared.idle) < shared.config.max_idle:
                shared.idle.append(_Idle(connection, self._made, time.monotonic()))
                connection = None
            else:
                shared.made = max(shared.made - 1, 0)
            shared.returned.notify()
        if connection is not None:
            connection.close()
