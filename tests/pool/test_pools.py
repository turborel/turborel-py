"""Tests of pools, over connections of the test's own."""

from __future__ import annotations

import copy
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import pytest

from turborel import OperationalError
from turborel._errors import connection_failure
from turborel._session.state import Session
from turborel.client import (
    DEFAULT_IDLE_TIMEOUT,
    DEFAULT_MAX,
    DEFAULT_MAX_LIFETIME,
    DEFAULT_WAIT,
    Pool,
    PoolConfig,
)

if TYPE_CHECKING:
    from turborel.client import Connection


@dataclass
class Fake:
    """A connection that answers a pool as told, keeping what it was asked."""

    granted: tuple[str, ...] = ("ping", "reset")
    is_lost: bool = False
    autocommit: bool = True
    authorization: str = "ANN"
    read_timeout: float | None = None
    fail_ping: bool = False
    fail_reset: bool = False
    asked: list[str] = field(default_factory=list)
    closed: bool = False
    _session: Session = field(default_factory=Session)

    def ping(self) -> None:
        """Pong, or a failure as told."""
        self.asked.append("ping")
        if self.fail_ping:
            raise connection_failure("no pong")

    def reset(self) -> None:
        """The session renewed, or a failure as told."""
        self.asked.append("reset")
        if self.fail_reset:
            raise connection_failure("no reset")

    def query(self, sql: str) -> None:
        """A statement run."""
        self.asked.append(sql)

    def set_read_timeout(self, seconds: float | None) -> None:
        """The read timeout changed."""
        self.read_timeout = seconds

    def close(self) -> None:
        """Closed."""
        self.closed = True


def maker(made: list[Fake], **fields: object) -> object:
    """A maker of fakes of `fields`, each kept in `made`."""

    def make() -> Connection:
        fake = Fake(**fields)  # type: ignore[arg-type]  # The fake's fields.
        made.append(fake)
        return cast("Connection", fake)

    return make


def test_the_defaults() -> None:
    """Verifies: [CLIENT Pools] `max` 10, `max_idle` 10, `idle_timeout` 10 minutes.

    `max_lifetime` an hour, `wait` 30 seconds, `check` yes, `reset` none.
    """
    config = PoolConfig()
    assert (config.max, config.max_idle) == (DEFAULT_MAX, DEFAULT_MAX) == (10, 10)
    assert (config.idle_timeout, config.max_lifetime) == (
        DEFAULT_IDLE_TIMEOUT,
        DEFAULT_MAX_LIFETIME,
    )
    assert (DEFAULT_IDLE_TIMEOUT, DEFAULT_MAX_LIFETIME, DEFAULT_WAIT) == (
        600.0,
        3600.0,
        30.0,
    )
    assert (config.check, config.reset) == (True, ())


def test_a_connection_handed_out_and_given_back() -> None:
    """Verifies: [CLIENT Pools] get an idle connection that answers, or make one.

    Given back as it is released, reset by Reset, autocommit off, then
    the `reset` statements; checked by Ping; a copy the same pool; a
    connection given back read no more.
    """
    made: list[Fake] = []
    pool = Pool(maker(made), PoolConfig(reset=("SET SCHEMA 'ANN'",)))  # type: ignore[arg-type]
    with pool.get() as first:
        assert pool.counts() == (1, 0)
        assert first.authorization == "ANN"
    assert made[0].asked == ["reset", "SET SCHEMA 'ANN'"]
    assert made[0].autocommit is False
    assert pool.counts() == (1, 1)
    twin = copy.copy(pool)
    again = twin.get()
    assert again.connection is cast("Connection", made[0])
    assert made[0].asked[-1] == "ping"
    again.release()
    again.release()
    with pytest.raises(OperationalError, match="given back to its pool"):
        _ = again.authorization
    assert len(made) == 1


def test_connections_closed_rather_than_kept() -> None:
    """Verifies: [CLIENT Pools] connections closed, not kept.

    Or beyond `max_idle`; one idle past `idle_timeout`, or failing its
    check, closed as get meets it.
    """
    made: list[Fake] = []
    pool = Pool(maker(made, fail_reset=True))  # type: ignore[arg-type]
    pool.get().release()
    assert (made[0].closed, pool.counts()) == (True, (0, 0))
    made.clear()
    old = Pool(maker(made), PoolConfig(max_lifetime=0.0))  # type: ignore[arg-type]
    old.get().release()
    assert made[0].closed
    made.clear()
    few = Pool(maker(made), PoolConfig(max_idle=1))  # type: ignore[arg-type]
    one, two = few.get(), few.get()
    one.release()
    two.release()
    assert (made[0].closed, made[1].closed, few.counts()) == (False, True, (1, 1))
    made.clear()
    stale = Pool(maker(made), PoolConfig(idle_timeout=0.0))  # type: ignore[arg-type]
    stale.get().release()
    stale.get().release()
    assert (len(made), made[0].closed) == (2, True)
    made.clear()
    checked = Pool(maker(made), PoolConfig())  # type: ignore[arg-type]
    checked.get().release()
    made[0].fail_ping = True
    checked.get().release()
    assert (len(made), made[0].closed) == (2, True)
    made.clear()
    lost = Pool(maker(made))  # type: ignore[arg-type]
    held = lost.get()
    made[0].is_lost = True
    held.release()
    assert made[0].closed


def test_get_waits_then_fails() -> None:
    """Verifies: [CLIENT Pools] get waits for one to come back, else fails (08001).

    Within `wait`; or with the failure of making one; no thread started
    by the pool, each wait the waiter's own.
    """
    made: list[Fake] = []
    pool = Pool(maker(made), PoolConfig(max=1, wait=0.05))  # type: ignore[arg-type]
    held = pool.get()
    before = threading.active_count()
    started = time.monotonic()
    with pytest.raises(OperationalError) as none:
        pool.get()
    assert none.value.sqlstate == "08001"
    assert time.monotonic() - started >= 0.05
    assert threading.active_count() == before
    waiting = Pool(maker(made), PoolConfig(max=1, wait=5.0))  # type: ignore[arg-type]
    first = waiting.get()
    got: list[object] = []
    taker = threading.Thread(target=lambda: got.append(waiting.get()))
    taker.start()
    time.sleep(0.05)
    first.release()
    taker.join(timeout=5)
    assert len(got) == 1
    held.release()

    def refuse() -> Connection:
        raise connection_failure("unreachable")

    failing = Pool(refuse)
    with pytest.raises(OperationalError, match="unreachable"):
        failing.get()
    assert failing.counts() == (0, 0)


def test_a_pool_of_settings_or_a_maker() -> None:
    """Verifies: [CLIENT Pools] a pool of settings, or a maker.

    An object of a `connect` method, as settings are, or a function.
    """
    made: list[Fake] = []

    class Maker:
        def connect(self) -> Connection:
            return cast("Connection", Fake())

    Pool(Maker()).get().release()
    Pool(maker(made)).get().release()  # type: ignore[arg-type]
    assert len(made) == 1


def test_a_pool_closed() -> None:
    """Verifies: [CLIENT Pools] its idle connections closed as it is done with.

    Those handed out closed as they are released.
    """
    made: list[Fake] = []
    with Pool(maker(made)) as pool:  # type: ignore[arg-type]
        kept, out = pool.get(), pool.get()
        kept.release()
    assert (made[0].closed, made[1].closed, pool.counts()) == (True, False, (1, 0))
    out.release()
    assert (made[1].closed, pool.counts()) == (True, (0, 0))


def test_a_pooled_connection_stands_for_its_connection() -> None:
    """Verifies: [CLIENT Pools] attributes its connection's."""
    made: list[Fake] = []
    pool = Pool(maker(made))  # type: ignore[arg-type]
    with pool.get() as pooled:
        pooled.autocommit = True
        assert made[0].autocommit is True
    with pytest.raises(OperationalError):
        pooled.autocommit = False
