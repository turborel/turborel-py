"""A connection of the asyncio interface: a session over an asyncio stream.

It runs the low-level client's own requests, the same steps the
blocking connection runs, each awaited: statements, prepared statements,
pipelines, Ping, Reset; and ends the session by Terminate.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from turborel._aio.runner import run
from turborel._codec import requests
from turborel._errors import Error
from turborel._pipeline import pipelines
from turborel._session import ops
from turborel._session.state import Session
from turborel._statements import prepared, queries
from turborel._transport.timeouts import TERMINATE_WITHIN

if TYPE_CHECKING:
    from collections.abc import Sequence

    from turborel._aio.streams import AsyncStream
    from turborel._auth.mechanisms import Mechanism
    from turborel._session.capabilities import Offer
    from turborel._session.ops import Steps
    from turborel._statements.prepared import Statement
    from turborel._statements.queries import Outcome
    from turborel._transport.target import Target

_T = TypeVar("_T")


class AsyncClient:
    """A session of a turborel server, over an asyncio stream."""

    def __init__(self, stream: AsyncStream, target: Target | None) -> None:
        """A connection over `stream`, reached at `target`, not yet logged in."""
        self._stream = stream
        self._target = target
        self._session = Session()
        self._read_timeout: float | None = None

    def __repr__(self) -> str:
        """Where it is connected, and as whom."""
        return f"AsyncClient({self._target!r}, {self._session.authorization!r})"

    async def _run(self, steps: Steps[_T]) -> _T:
        return await run(self._stream, self._session, steps)

    async def log_in(self, user: str, mechanism: Mechanism, offer: Offer) -> None:
        """Log `user` in, proved by `mechanism`, asking `offer`.

        Raises:
            Error: As the server refuses, or the connection fails.
        """
        try:
            await self._run(ops.login(self._session, user, mechanism, offer))
        except Error:
            self._stream.close()
            raise

    @property
    def authorization(self) -> str:
        """The session's user, as Ready told it."""
        return self._session.authorization

    @property
    def target(self) -> Target | None:
        """Where it reached its server."""
        return self._target

    @property
    def granted(self) -> tuple[str, ...]:
        """The capabilities granted, in Ready's order."""
        return self._session.told.granted

    @property
    def in_transaction(self) -> bool:
        """Whether the session's transaction is active, as the server last said."""
        return self._session.active

    @property
    def is_lost(self) -> bool:
        """Whether the connection is lost."""
        return self._session.is_lost()

    @property
    def autocommit(self) -> bool:
        """Whether each statement is its own transaction."""
        return self._session.autocommit

    @autocommit.setter
    def autocommit(self, on: bool) -> None:
        self._session.autocommit = on

    @property
    def warning(self) -> str | None:
        """The SQLSTATE of the last statement's warning, if it warned."""
        return self._session.warning

    @property
    def last_generated(self) -> tuple[str, ...]:
        """The identity values the last INSERT generated, as SQL writes them."""
        completed = self._session.told.completed
        return () if completed is None else completed.generated

    def set_read_timeout(self, within: float | None) -> None:
        """Bound each read after login to `within` seconds; None for no limit."""
        self._read_timeout = within
        self._stream.set_timeout(within)

    def setting(self, name: str) -> str | None:
        """A session setting, as the server last told it."""
        return self._session.told.settings.get(name)

    async def query(self, sql: str) -> Outcome:
        """Run one statement: a query's rows, or its completion."""
        return await self._run(queries.query(self._session, sql))

    async def prepare(self, sql: str) -> Statement:
        """Prepare `sql`."""
        return await self._run(prepared.prepare(self._session, sql))

    async def execute(self, statement: Statement, values: Sequence[object]) -> Outcome:
        """Execute `statement` with `values`."""
        return await self._run(prepared.execute(self._session, statement, values))

    async def deallocate(self, statement: Statement) -> None:
        """Destroy a prepared statement."""
        await self._run(prepared.deallocate(self._session, statement))

    async def pipeline(
        self, queued: Sequence[pipelines.Queued], *, skip: bool
    ) -> list[object]:
        """Run `queued` as a pipeline does: one outcome each, in order."""
        return await self._run(pipelines.run(self._session, queued, skip=skip))

    async def ping(self) -> None:
        """Ping the server."""
        await self._run(ops.ping(self._session))

    async def reset(self) -> None:
        """Reset the session."""
        await self._run(ops.reset(self._session))

    async def terminate(self) -> None:
        """End the session, waiting for the close the read timeout, else 60 seconds.

        Raises:
            Error: The failure of the commit the end made, or the connection's.
        """
        session = self._session
        if session.lost is not None:
            raise session.lost
        try:
            await self._stream.write(requests.Terminate().encode())
            self._stream.set_timeout(self._read_timeout or TERMINATE_WITHIN)
            while (
                frame := await self._stream.read_frame_or_end(session.max_body)
            ) is not None:
                ops.terminated(session, frame)
        finally:
            self._stream.close()
            session.lose_by("the session was terminated")

    def close(self) -> None:
        """Close the connection without ending the session first."""
        self._stream.close()
        if self._session.lost is None:
            self._session.lose_by("the connection was closed")
