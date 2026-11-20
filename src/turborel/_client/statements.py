"""A connection's statements, and what each one's completion told.

[CLIENT Running statements] [CLIENT Prepared statements] [CLIENT What
the server tells] [CLIENT Controlling the session]
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from turborel._client.core import Core
from turborel._pipeline.pipelines import Pipeline
from turborel._session.capabilities import QUERY_ATTRIBUTES
from turborel._statements import prepared, queries

if TYPE_CHECKING:
    from collections.abc import Sequence

    from turborel._codec.composites import Column
    from turborel._codec.failures import Failure
    from turborel._codec.replies import Complete, Timing
    from turborel._statements.prepared import Batch, Statement
    from turborel._statements.queries import Outcome, Ran, Sink


class Statements(Core):
    """What a connection runs: queries, prepared statements and cursors."""

    def query(self, sql: str) -> Outcome:
        """Run one statement: a query's columns and rows, or its completion.

        Raises:
            Error: The statement's failure, or the connection's.
        """
        return self._run(queries.query(self._session, sql))

    def query_into(self, sql: str, sink: Sink) -> int | Complete:
        """Run one statement, its rows given to `sink` a batch at a time, as they come.

        Returns:
            The rows given, of a query; the completion of another statement.

        Raises:
            Error: The statement's failure, or the connection's.
        """
        return self._run(queries.query_into(self._session, sql, sink))

    def query_many(self, sql: str) -> Ran:
        """Run a text of several statements as one request, until one fails.

        Raises:
            Error: If `multi-statement` was not granted, or the connection is
                lost; a statement's failure is the `Ran`'s.
        """
        return self._run(queries.query_many(self._session, sql))

    def pipeline(self) -> Pipeline:
        """An empty pipeline of requests on this connection, continuing on error."""
        return Pipeline(self)

    def prepare(self, sql: str) -> Statement:
        """Prepare `sql`, its dynamic parameters written `?`.

        Raises:
            Error: The statement's failure, or the connection's.
        """
        return self._run(prepared.prepare(self._session, sql))

    def execute(self, statement: Statement, values: Sequence[object] = ()) -> Outcome:
        """Execute `statement` with `values` for its `?` marks.

        Raises:
            Error: The statement's failure, or the connection's.
        """
        return self._run(prepared.execute(self._session, statement, values))

    def open_cursor(
        self,
        statement: Statement,
        values: Sequence[object] = (),
        rows: int = 0,
        cursor: int = 0,
    ) -> Batch:
        """Open a query's cursor, numbered `cursor`, and take its first `rows` rows.

        A cursor other than 0 needs `cursors`; 0 rows is all of them.

        Raises:
            Error: The statement's failure, or the connection's.
        """
        steps = prepared.open_cursor(self._session, (statement, cursor), values, rows)
        return self._run(steps)

    def fetch(self, statement: Statement, rows: int = 0, cursor: int = 0) -> Batch:
        """The next `rows` rows of an open cursor; 0 for all.

        Raises:
            Error: If the cursor is not open (24000), or the connection's.
        """
        return self._run(prepared.fetch(self._session, (statement, cursor), rows))

    def close_cursor(self, statement: Statement, cursor: int = 0) -> None:
        """Close an open cursor.

        Raises:
            Error: If it is not open, or the connection's.
        """
        self._run(prepared.close(self._session, (statement, cursor)))

    def describe(self, statement: Statement) -> Statement:
        """Describe a prepared statement again, with `describe`.

        Raises:
            Error: If `describe` was not granted, or the connection's.
        """
        return self._run(prepared.describe(self._session, statement))

    def describe_cursor(
        self, statement: Statement, cursor: int = 0
    ) -> tuple[Column, ...]:
        """An open cursor's columns, with `describe`.

        Raises:
            Error: If `describe` was not granted, or the cursor is not open.
        """
        return self._run(prepared.describe_cursor(self._session, (statement, cursor)))

    def deallocate(self, statement: Statement) -> None:
        """Destroy a prepared statement.

        Raises:
            Error: If there is none such (26000), or a cursor of it is open.
        """
        self._run(prepared.deallocate(self._session, statement))

    def set_query_attributes(self, attributes: Sequence[tuple[str, str]]) -> None:
        """Attributes every later statement carries, until set again.

        Raises:
            OperationalError: SQLSTATE 08006, if `query-attributes` was not
                granted and `attributes` are some.
        """
        self._session.needs(QUERY_ATTRIBUTES, ok=not attributes)
        self._session.told.attributes = tuple(attributes)

    @property
    def warning(self) -> str | None:
        """The SQLSTATE of the last statement's warning, of class 01, if it warned."""
        return self._session.warning

    @property
    def rows_affected(self) -> int | None:
        """The rows the last statement changed or a query gave, with `row-counts`."""
        completed = self._session.told.completed
        return None if completed is None else completed.rows

    @property
    def last_generated(self) -> tuple[str, ...]:
        """The identity values the last INSERT generated, as SQL writes them."""
        completed = self._session.told.completed
        return () if completed is None else completed.generated

    @property
    def server_time(self) -> Timing | None:
        """The server's time for the last statement, in µs, with `row-counts`."""
        completed = self._session.told.completed
        return None if completed is None else completed.time

    @property
    def commit_position(self) -> int | None:
        """The log position of the last commit, with `commit-position`."""
        return self._session.told.position

    @property
    def conditions(self) -> tuple[Failure, ...]:
        """The last statement's conditions, with `conditions`."""
        completed = self._session.told.completed
        return () if completed is None else completed.conditions
