"""A connection's bulk work: copying rows in, and exporting a query's.

[CLIENT Copying and exporting] [PROTOCOL CopyIn 'I'] [PROTOCOL CopyData
'J'] [PROTOCOL CopyEnd 'N']
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Self, TypeVar

from turborel._client.lobs import LargeObjects
from turborel._codec import requests
from turborel._codec.replies import Complete
from turborel._copy import copying
from turborel._copy.exporting import ExportFormat, Writer
from turborel._errors import connection_failure, misuse
from turborel._session import ops
from turborel._session.runner import run

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from types import TracebackType
    from typing import BinaryIO

    from turborel._session.ops import Steps

_T = TypeVar("_T")


class Bulk(LargeObjects):
    """What a connection does in bulk."""

    def _run(self, steps: Steps[_T]) -> _T:
        if self._session.copying:
            steps.close()
            msg = "a copy is under way: finish or abandon it first"
            raise misuse(msg)
        return super()._run(steps)

    def _run_copying(self, steps: Steps[_T]) -> _T:
        return run(self._stream, self._session, steps)

    def copy_in(self, table: str, columns: Sequence[str] = ()) -> Copying:
        """Begin a copy into `table`, as SQL names it, of `columns`, all if none.

        Under autocommit the copy is its own transaction. Until it is
        finished or abandoned, the connection takes only the copy's rows
        and Ping.

        Raises:
            OperationalError: SQLSTATE 08006, if `copy` was not granted; the
                connection's. The table not found, or a column not of it,
                comes as `finish`'s failure.
        """
        return self._copy_begin(table, columns, ends=self.autocommit)

    def _copy_begin(self, table: str, columns: Sequence[str], *, ends: bool) -> Copying:
        self._run(copying.begin(self._session, table, columns, ends=ends))
        self._session.copying = True
        return Copying(self)

    def copy_rows(
        self, table: str, columns: Sequence[str], rows: Iterable[Sequence[object]]
    ) -> int:
        """Copy `rows` into `table`'s `columns`, as `copy_in` does: the rows inserted.

        Raises:
            Error: As `copy_in`'s and `Copying.finish`'s.
        """
        with self.copy_in(table, columns) as copy:
            for row in rows:
                copy.send(row)
            return copy.finish()

    def export(
        self, sql: str, out: BinaryIO, form: ExportFormat = ExportFormat.CSV
    ) -> int:
        """Run the query `sql` and write its rows to `out` as `form` says, as they come.

        Returns:
            The rows written.

        Raises:
            Error: The query's; SQLSTATE 08006 of a statement that is no
                query, or a write to `out` that failed, which ends the
                export and not the connection.
        """
        writer = Writer(out, form)
        if form is ExportFormat.NATIVE:
            self._session.tap = writer.frame
        try:
            streamed = self.query_into(sql, writer)
        finally:
            self._session.tap = None
        if isinstance(streamed, Complete):
            msg = "an export runs a query"
            raise connection_failure(msg)
        writer.finish()
        return streamed


class Copying:
    """A copy under way, over its connection.

    As a context manager, a copy left neither finished nor abandoned is
    abandoned, so the connection takes requests again.
    """

    def __init__(self, connection: Bulk) -> None:
        """A copy begun over `connection`."""
        self._connection = connection
        self._waiting: list[bytes] = []
        self._octets = 0
        self._ended = False

    def __enter__(self) -> Self:
        """The copy."""
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Abandon the copy, unless it ended."""
        if not self._ended and not self._connection.is_lost:
            self.abandon()

    def send(self, row: Sequence[object]) -> None:
        """Send `row`, with those before it once they are 256 KiB.

        Raises:
            Error: A value that cannot be sent; the connection's. A row the
                server refuses comes as `finish`'s failure.
        """
        encoded = requests.encoded_row(row)
        self._waiting.append(encoded)
        self._octets += len(encoded)
        if self._octets >= copying.CHUNK_BYTES:
            self._flush()

    def ping(self) -> None:
        """Ping the server during the copy [PROTOCOL Ping 'G'].

        Raises:
            Error: As `Connection.ping`'s.
        """
        self._flush()
        self._connection._run_copying(ops.ping(self._connection._session))  # noqa: SLF001

    def finish(self) -> int:
        """End the copy: the rows inserted.

        Raises:
            Error: The copy's failure, every row of it undone: the table or a
                column not found, a row of too many or too few values, a
                value its column refuses, its detail naming the row; the
                connection's.
        """
        self._flush()
        return self._end(abandon=False)

    def abandon(self) -> None:
        """Give the copy up: every row of it undone.

        Raises:
            Error: The connection's.
        """
        self._end(abandon=True)

    @property
    def ended(self) -> bool:
        """Whether the copy ended, finished or abandoned."""
        return self._ended

    def _flush(self) -> None:
        if self._waiting:
            rows, self._waiting, self._octets = self._waiting, [], 0
            self._connection._run_copying(copying.data(rows))  # noqa: SLF001

    def _end(self, *, abandon: bool) -> int:
        self._ended = True
        session = self._connection._session  # noqa: SLF001
        try:
            return self._connection._run_copying(copying.end(session, abandon=abandon))  # noqa: SLF001
        finally:
            session.copying = False
