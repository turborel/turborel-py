"""DB-API 2.0 (PEP 249): `connect`, the connection and the cursor [DESIGN] D2.

`connect` connects as settings say: a `turborel://` URI, or settings by
their names, laid over a service's and the environment's
([CLIENT Connecting by settings]). The connection begins a transaction
with its first statement, as Turborel does, and ends it by `commit` or
`rollback`; one closed with a transaction active rolls it back, as PEP
249 says. A cursor runs a statement with parameters by preparing it
once, the connection keeping its statements by text, and executing it
with the values, each `?` one; without parameters, as a direct
statement. `executemany` executes once for each set of values, in one
pipeline that stops at the first failure, those after it undone.
Everything the standard API has no place for
is the low-level client's, reached by the connection's `client`.
"""

from __future__ import annotations

from collections import OrderedDict
from typing import TYPE_CHECKING, Final, Self

from turborel._api import calls
from turborel._api.results import ARRAYSIZE, Results, parameters_of
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
from turborel._pipeline.pipelines import OnError
from turborel._settings.options import Options
from turborel._settings.settings import Settings

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from types import TracebackType

    from turborel._api.calls import ParameterDescription
    from turborel._api.results import Description
    from turborel._client.connection import Connection as Client
    from turborel._statements.prepared import Statement
    from turborel._statements.queries import Outcome

KEPT_STATEMENTS: Final = 128
"""The statements a connection keeps prepared, by their text."""
STATEMENT_GONE: Final = "26000"
"""SQLSTATE 26000: a prepared statement the server no longer has."""


def options_of(dsn: str | None, settings: dict[str, object]) -> Options:
    """The program's options: `dsn`'s, a URI's, with `settings` laid over them.

    Raises:
        OperationalError: SQLSTATE 08001, of a URI or a setting that
            cannot be read.
    """
    options = Options.from_uri(dsn) if dsn else Options()
    for key, value in settings.items():
        if value is not None:
            options.set(
                key, str(value).lower() if isinstance(value, bool) else str(value)
            )
    return options


def connect(dsn: str | None = None, **settings: object) -> Connection:
    """A connection, as the settings say [DESIGN] D2.

    `dsn` is a `turborel://` URI; `settings`, settings by their names,
    `host`, `port`, `user`, `password`, `tls_mode` and the rest, over
    it; then a service's, the environment's and the defaults.

    Raises:
        OperationalError: SQLSTATE 08001, of settings that cannot be read
            or no server kept; 28000 of a user refused.
        Error: As the server refuses the login.
    """
    return Connection(Settings.resolve(options_of(dsn, settings)).connect())


class Statements:
    """A connection's statements prepared, by text, the least used let go first."""

    def __init__(self) -> None:
        self.kept: OrderedDict[str, Statement] = OrderedDict()

    def get(self, sql: str) -> Statement | None:
        found = self.kept.get(sql)
        if found is not None:
            self.kept.move_to_end(sql)
        return found

    def put(self, sql: str, statement: Statement) -> Statement | None:
        """Keep `statement`; the one let go to make room, if any."""
        self.kept[sql] = statement
        if len(self.kept) > KEPT_STATEMENTS:
            return self.kept.popitem(last=False)[1]
        return None

    def forget(self, sql: str) -> None:
        self.kept.pop(sql, None)


class Connection:
    """A connection of the standard API, over a connection of the low-level client."""

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

    def __init__(self, client: Client) -> None:
        """The standard API's connection over `client`."""
        self._client: Client | None = client
        self._statements = Statements()

    def __enter__(self) -> Self:
        """The connection."""
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Commit, or of an exception roll back; then close."""
        try:
            if kind is None:
                self.commit()
        finally:
            self.close()

    @property
    def client(self) -> Client:
        """The low-level client's connection, for all the standard API has no place for.

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
        """Whether each statement is its own transaction; off by default (PEP 249)."""
        return self.client.autocommit

    @autocommit.setter
    def autocommit(self, on: bool) -> None:
        self.client.autocommit = on

    @property
    def in_transaction(self) -> bool:
        """Whether a transaction is active, as the server last said."""
        return self.client.in_transaction

    def cursor(self) -> Cursor:
        """A new cursor of this connection.

        Raises:
            InterfaceError: SQLSTATE TB910, once the connection is closed.
        """
        return Cursor(self, self.client)

    def commit(self) -> None:
        """Commit the transaction, if one is active.

        Raises:
            Error: The commit's failure.
        """
        if self.client.in_transaction:
            self.client.query("COMMIT")

    def rollback(self) -> None:
        """Roll the transaction back, if one is active.

        Raises:
            Error: The rollback's failure.
        """
        if self.client.in_transaction:
            self.client.query("ROLLBACK")

    def close(self) -> None:
        """Close it, an active transaction rolled back first; again, nothing."""
        client, self._client = self._client, None
        if client is None:
            return
        try:
            if client.in_transaction and not client.is_lost:
                client.query("ROLLBACK")
            if not client.is_lost:
                client.terminate()
        except Error:
            client.close()

    def _prepared(self, sql: str) -> Statement:
        found = self._statements.get(sql)
        if found is not None:
            return found
        statement = self.client.prepare(sql)
        dropped = self._statements.put(sql, statement)
        if dropped is not None:
            self.client.deallocate(dropped)
        return statement

    def _execute(self, sql: str, values: tuple[object, ...]) -> Outcome:
        statement = self._prepared(sql)
        try:
            return self.client.execute(statement, values)
        except ProgrammingError as e:
            if e.sqlstate != STATEMENT_GONE:
                raise
            # Gone with a reset of the session: prepared again, once.
            self._statements.forget(sql)
            return self.client.execute(self._prepared(sql), values)

    def _call(self, sql: str, values: tuple[object, ...]) -> tuple[Statement, Outcome]:
        statement = self._prepared(sql)
        try:
            return statement, self.client.execute(
                statement, calls.inputs_of(statement, values)
            )
        except ProgrammingError as e:
            if e.sqlstate != STATEMENT_GONE:
                raise
            # Gone with a reset of the session: prepared again, once.
            self._statements.forget(sql)
            statement = self._prepared(sql)
            inputs = calls.inputs_of(statement, values)
            return statement, self.client.execute(statement, inputs)

    def _execute_many(
        self, sql: str, sets: Sequence[tuple[object, ...]]
    ) -> list[Outcome]:
        statement = self._prepared(sql)
        pipeline = self.client.pipeline().on_error(OnError.SKIP)
        for values in sets:
            pipeline.execute(statement, values)
        outcomes = pipeline.run()
        for outcome in outcomes:
            if isinstance(outcome, Error):
                raise outcome
        return outcomes  # type: ignore[return-value]  # None failed, none skipped.


class Cursor:
    """A cursor of the standard API: a statement run, its rows fetched in order."""

    def __init__(self, connection: Connection, client: Client) -> None:
        """A cursor of `connection`, over its `client`."""
        self.connection = connection
        self._client: Client | None = client
        self._results = Results()
        self.arraysize = ARRAYSIZE

    def __enter__(self) -> Self:
        """The cursor."""
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close it."""
        self.close()

    def __iter__(self) -> Iterator[tuple[object, ...]]:
        """Its rows, from the next."""
        while (row := self.fetchone()) is not None:
            yield row

    @property
    def description(self) -> tuple[Description, ...] | None:
        """The last query's columns, seven items each; None of another statement."""
        return self._results.description

    @property
    def parameters(self) -> tuple[ParameterDescription, ...] | None:
        """Each `?` of the last `callproc`, its mode, position and type; else None."""
        return self._results.parameters

    @property
    def rowcount(self) -> int:
        """The rows the last statement gave or changed; -1 if not told."""
        return self._results.rowcount

    @property
    def warning(self) -> str | None:
        """The SQLSTATE of the last statement's warning, of class 01, if it warned."""
        return self._open().warning

    @property
    def last_generated(self) -> tuple[str, ...]:
        """The identity values the last INSERT generated, as SQL writes them."""
        return self._open().last_generated

    def _open(self) -> Client:
        if self._client is None or self.connection.closed:
            msg = "the cursor is closed"
            raise misuse(msg)
        return self._client

    def execute(
        self, operation: str, parameters: Sequence[object] | None = None
    ) -> Self:
        """Run `operation`, each `?` of it a value of `parameters`, in order.

        Raises:
            InterfaceError: SQLSTATE TB910, of a closed cursor, or parameters
                that are not a sequence.
            Error: The statement's failure.
        """
        self._open()
        values = parameters_of(parameters)
        if not values:
            outcome = self._open().query(operation)
        else:
            outcome = self.connection._execute(operation, values)  # noqa: SLF001
        self._results.take(outcome)
        return self

    def callproc(
        self, procname: str, parameters: Sequence[object] | None = None
    ) -> tuple[object, ...]:
        """Call the procedure `procname` with a value for each argument, in order.

        A value of an OUT parameter is given and not sent, as None, say.
        Returns the values given, each of an OUT or INOUT parameter replaced
        by what the procedure returned; that row is fetched too.

        Raises:
            InterfaceError: SQLSTATE TB910, of a closed cursor, a name not a
                procedure's, or a count of values not its arguments'.
            Error: The call's failure.
        """
        self._open()
        values = parameters_of(parameters) or ()
        sql = calls.call_text(procname, len(values))
        statement, outcome = self.connection._call(sql, values)  # noqa: SLF001
        self._results.take(outcome)
        self._results.parameters = calls.described(statement)
        return calls.returned(statement, values, outcome)

    def executemany(
        self, operation: str, seq_of_parameters: Sequence[Sequence[object]]
    ) -> Self:
        """Run `operation` for each set of values, one pipeline, stopping at a failure.

        Raises:
            Error: The first failure, the executions after it undone, those
                before it kept in the transaction.
        """
        self._open()
        sets = [parameters_of(p) or () for p in seq_of_parameters]
        if not sets:
            self._results.counted([])
            return self
        outcomes = self.connection._execute_many(operation, sets)  # noqa: SLF001
        self._results.counted(outcomes)
        return self

    def fetchone(self) -> tuple[object, ...] | None:
        """The next row, or None at the end.

        Raises:
            InterfaceError: SQLSTATE TB910, if the last statement was no query.
        """
        self._open()
        return self._results.fetchone()

    def fetchmany(self, size: int | None = None) -> list[tuple[object, ...]]:
        """The next `size` rows, `arraysize` by default; fewer at the end."""
        self._open()
        return self._results.fetch(self.arraysize if size is None else size)

    def fetchall(self) -> list[tuple[object, ...]]:
        """The rest of the rows."""
        self._open()
        return self._results.fetch(None)

    def setinputsizes(self, sizes: object) -> None:
        """Nothing: the server gives each parameter's type."""

    def setoutputsize(self, size: int, column: int | None = None) -> None:
        """Nothing: every value is read whole."""

    def close(self) -> None:
        """Close it; closing it again does nothing."""
        self._client = None
        self._results = Results()
