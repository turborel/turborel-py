"""turborel.aio: the standard API for asyncio, its waits coroutines [DESIGN] D2.

The same objects as PEP 249's, in `turborel`: `connect`, a connection
and its cursors, the same exceptions, type objects and constructors;
each method that waits on the server is a coroutine, run by the same
requests as the blocking interface's, each step awaited. A connection
begins a transaction with its first statement and ends it by `commit`
or `rollback`; one closed with a transaction active rolls it back.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Self

from turborel._aio.connect import connect as connect_settings
from turborel._api.dbapi import KEPT_STATEMENTS, STATEMENT_GONE, Statements, options_of
from turborel._api.results import ARRAYSIZE, Results, parameters_of
from turborel._api.types import (
    BINARY,
    DATETIME,
    NUMBER,
    ROWID,
    STRING,
    Binary,
    Date,
    DateFromTicks,
    Time,
    TimeFromTicks,
    Timestamp,
    TimestampFromTicks,
)
from turborel._errors import (
    DatabaseError,
    DataError,
    Error,
    IntegrityError,
    InterfaceError,
    InternalError,
    NotSupportedError,
    OperationalError,
    ProgrammingError,
    Warning,  # noqa: A004  # PEP 249 names it.
    misuse,
)
from turborel._pipeline.pipelines import Execute
from turborel._settings.settings import Settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence
    from types import TracebackType

    from turborel._aio.client import AsyncClient
    from turborel._api.results import Description
    from turborel._statements.prepared import Statement
    from turborel._statements.queries import Outcome

apilevel: Final = "2.0"
"""The DB-API level the interface follows, PEP 249's 2.0."""
paramstyle: Final = "qmark"
"""Parameters are marked `?`."""
threadsafety: Final = 1
"""Tasks of one loop may share the module, not a connection."""


async def connect(dsn: str | None = None, **settings: object) -> Connection:
    """A connection, as the settings say, as `turborel.connect` makes one.

    Raises:
        OperationalError: SQLSTATE 08001, of settings that cannot be read
            or no server kept; 28000 of a user refused.
        Error: As the server refuses the login.
    """
    return Connection(
        await connect_settings(Settings.resolve(options_of(dsn, settings)))
    )


class Connection:
    """A connection of the asyncio interface."""

    Warning = Warning
    Error = Error
    InterfaceError = InterfaceError
    DatabaseError = DatabaseError
    DataError = DataError
    OperationalError = OperationalError
    IntegrityError = IntegrityError
    InternalError = InternalError
    ProgrammingError = ProgrammingError
    NotSupportedError = NotSupportedError

    def __init__(self, client: AsyncClient) -> None:
        """The asyncio interface's connection over `client`."""
        self._client: AsyncClient | None = client
        self._statements = Statements()

    async def __aenter__(self) -> Self:
        """The connection."""
        return self

    async def __aexit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Commit, or of an exception roll back; then close."""
        try:
            if kind is None:
                await self.commit()
        finally:
            await self.close()

    @property
    def client(self) -> AsyncClient:
        """The asyncio client's connection.

        Raises:
            InterfaceError: SQLSTATE TB910, once the connection is closed.
        """
        if self._client is None:
            msg = "the connection is closed"
            raise misuse(msg)
        return self._client

    @property
    def closed(self) -> bool:
        """Whether it is closed."""
        return self._client is None

    @property
    def autocommit(self) -> bool:
        """Whether each statement is its own transaction; off by default."""
        return self.client.autocommit

    @autocommit.setter
    def autocommit(self, on: bool) -> None:
        self.client.autocommit = on

    @property
    def in_transaction(self) -> bool:
        """Whether a transaction is active, as the server last said."""
        return self.client.in_transaction

    def cursor(self) -> Cursor:
        """A new cursor of this connection."""
        return Cursor(self, self.client)

    async def commit(self) -> None:
        """Commit the transaction, if one is active."""
        if self.client.in_transaction:
            await self.client.query("COMMIT")

    async def rollback(self) -> None:
        """Roll the transaction back, if one is active."""
        if self.client.in_transaction:
            await self.client.query("ROLLBACK")

    async def close(self) -> None:
        """Close it, an active transaction rolled back first; again, nothing."""
        client, self._client = self._client, None
        if client is None:
            return
        try:
            if client.in_transaction and not client.is_lost:
                await client.query("ROLLBACK")
            if not client.is_lost:
                await client.terminate()
        except Error:
            client.close()

    async def _prepared(self, sql: str) -> Statement:
        found = self._statements.get(sql)
        if found is not None:
            return found
        statement = await self.client.prepare(sql)
        dropped = self._statements.put(sql, statement)
        if dropped is not None:
            await self.client.deallocate(dropped)
        return statement

    async def _execute(self, sql: str, values: tuple[object, ...]) -> Outcome:
        statement = await self._prepared(sql)
        try:
            return await self.client.execute(statement, values)
        except ProgrammingError as e:
            if e.sqlstate != STATEMENT_GONE:
                raise
            self._statements.forget(sql)
            return await self.client.execute(await self._prepared(sql), values)

    async def _execute_many(
        self, sql: str, sets: Sequence[tuple[object, ...]]
    ) -> list[Outcome]:
        statement = await self._prepared(sql)
        outcomes = await self.client.pipeline(
            [Execute(statement, v) for v in sets], skip=True
        )
        for outcome in outcomes:
            if isinstance(outcome, Error):
                raise outcome
        return outcomes  # type: ignore[return-value]  # None failed, none skipped.


class Cursor:
    """A cursor of the asyncio interface: a statement run, its rows fetched in order."""

    def __init__(self, connection: Connection, client: AsyncClient) -> None:
        """A cursor of `connection`, over its `client`."""
        self.connection = connection
        self._client: AsyncClient | None = client
        self._results = Results()
        self.arraysize = ARRAYSIZE

    async def __aenter__(self) -> Self:
        """The cursor."""
        return self

    async def __aexit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close it."""
        await self.close()

    async def __aiter__(self) -> AsyncIterator[tuple[object, ...]]:
        """Its rows, from the next."""
        while (row := await self.fetchone()) is not None:
            yield row

    @property
    def description(self) -> tuple[Description, ...] | None:
        """The last query's columns, seven items each; None of another statement."""
        return self._results.description

    @property
    def rowcount(self) -> int:
        """The rows the last statement gave or changed; -1 if not told."""
        return self._results.rowcount

    @property
    def warning(self) -> str | None:
        """The SQLSTATE of the last statement's warning, if it warned."""
        return self._open().warning

    @property
    def last_generated(self) -> tuple[str, ...]:
        """The identity values the last INSERT generated."""
        return self._open().last_generated

    def _open(self) -> AsyncClient:
        if self._client is None or self.connection.closed:
            msg = "the cursor is closed"
            raise misuse(msg)
        return self._client

    async def execute(
        self, operation: str, parameters: Sequence[object] | None = None
    ) -> Self:
        """Run `operation`, each `?` of it a value of `parameters`, in order."""
        client = self._open()
        values = parameters_of(parameters)
        if not values:
            outcome = await client.query(operation)
        else:
            outcome = await self.connection._execute(operation, values)  # noqa: SLF001
        self._results.take(outcome)
        return self

    async def executemany(
        self, operation: str, seq_of_parameters: Sequence[Sequence[object]]
    ) -> Self:
        """Run `operation` for each set of values, one pipeline, to a failure."""
        self._open()
        sets = [parameters_of(p) or () for p in seq_of_parameters]
        if not sets:
            self._results.counted([])
            return self
        self._results.counted(await self.connection._execute_many(operation, sets))  # noqa: SLF001
        return self

    async def fetchone(self) -> tuple[object, ...] | None:
        """The next row, or None at the end."""
        self._open()
        return self._results.fetchone()

    async def fetchmany(self, size: int | None = None) -> list[tuple[object, ...]]:
        """The next `size` rows, `arraysize` by default."""
        self._open()
        return self._results.fetch(self.arraysize if size is None else size)

    async def fetchall(self) -> list[tuple[object, ...]]:
        """The rest of the rows."""
        self._open()
        return self._results.fetch(None)

    def setinputsizes(self, sizes: object) -> None:
        """Nothing: the server gives each parameter's type."""

    def setoutputsize(self, size: int, column: int | None = None) -> None:
        """Nothing: every value is read whole."""

    async def close(self) -> None:
        """Close it."""
        self._client = None
        self._results = Results()


__all__ = [
    "BINARY",
    "DATETIME",
    "KEPT_STATEMENTS",
    "NUMBER",
    "ROWID",
    "STRING",
    "Binary",
    "Connection",
    "Cursor",
    "DataError",
    "DatabaseError",
    "Date",
    "DateFromTicks",
    "Error",
    "IntegrityError",
    "InterfaceError",
    "InternalError",
    "NotSupportedError",
    "OperationalError",
    "ProgrammingError",
    "Time",
    "TimeFromTicks",
    "Timestamp",
    "TimestampFromTicks",
    "Warning",
    "apilevel",
    "connect",
    "paramstyle",
    "threadsafety",
]
