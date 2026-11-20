"""Import: a source's records inserted into a table [CLIENT Importing].

Through one prepared INSERT, its columns the source's headings, or else
the table's, as a prepared query's description gives them; each value
cast by the server to its column's type, but a string for a character
string column, which is assigned to it as INSERT assigns, so one too
long is refused, not cut. A batch of rows is committed at a time; a
failure rolls the batch back and stops, or, if asked, a bad row is
skipped and reported, and the import goes on. Where the server grants
`copy`, no bad row is to be skipped and no column is a large object's,
the rows go by bulk copy, a batch to a copy [CLIENT Copying and
exporting].
"""

from __future__ import annotations

import contextlib
import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from turborel._codec.datatypes import CharacterType, LobType
from turborel._codec.failures import Diagnostics, Failure
from turborel._copy.names import column_name, delimited, table_name
from turborel._copy.sources import SourceError
from turborel._errors import DATA_SQLCODE, Error
from turborel._lobs.locators import LOB_INLINE_OCTETS
from turborel._session.capabilities import COPY
from turborel._session.raising import ends_connection, raised

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from turborel._client.bulk import Bulk, Copying
    from turborel._codec.composites import Parameter
    from turborel._copy.sources import Position, Record, Source
    from turborel._statements.prepared import Statement

DEFAULT_BATCH: Final = 1000
"""How many rows an import commits at a time, unless told."""
STRING_DATA_RIGHT_TRUNCATION: Final = "22001"
"""SQLSTATE 22001: a string too long for its column."""
DATA_EXCEPTION: Final = "22000"
"""SQLSTATE 22000: a data exception, an import's input that cannot be read."""
CANCELLED_SQLCODE: Final = -920
"""The SQLCODE of a statement cancelled."""
INSERT_ASSIGNS: Final = "ISO/IEC 9075:1992 §13.8 GR4b iii"
"""The rule by which INSERT assigns a value to its column."""
_PREFIX: Final = "ISO/IEC 9075:1992 "
_ROW: Final = "row "
_OF_THE_COPY: Final = " of the copy"


@dataclass(frozen=True, slots=True)
class Import:
    """What an import is to do: its table, its batch, whether bad rows are skipped."""

    table: str
    """The `<table name>` the rows go into, as SQL writes it."""
    batch: int = DEFAULT_BATCH
    """How many rows are committed at a time; 0 for all at once."""
    skip: bool = False
    """Whether a row refused is skipped and reported, rather than ending the import."""


@dataclass(frozen=True, slots=True)
class Imported:
    """What an import did: the rows inserted and committed, and those skipped."""

    rows: int
    rejected: int = 0


Cause = str | Error
"""Why a row, or an import, failed: the input's, in words, or an SQL condition."""


@dataclass(frozen=True, slots=True)
class Rejected:
    """A row skipped: where it began, and why."""

    position: Position
    cause: Cause

    def __str__(self) -> str:
        """As `record 2, line 3: why; skipped`."""
        return f"{self.position}: {_said(self.cause)}; skipped"


class ImportFailure(Error):  # noqa: N818  # ImportError is the builtin's.
    """Why an import stopped, where, and what of it was kept.

    Its SQLCODE and SQLSTATE are its SQL condition's, or of an input that
    cannot be read, a data exception's: -301, 22000.
    """

    def __init__(
        self, position: Position | None, cause: Cause, kept: tuple[int, int]
    ) -> None:
        """An import stopped at `position` for `cause`, `kept` its rows kept, undone."""
        committed, rolled_back = kept
        where = "" if position is None else f"{position}: "
        kept_text = f"{rows(committed)} committed, {rolled_back} rolled back"
        message = f"{where}{_said(cause)}; {kept_text}"
        if isinstance(cause, Error):
            super().__init__(
                message,
                sqlcode=cause.sqlcode,
                sqlstate=cause.sqlstate,
                failure=cause.failure,
            )
        else:
            super().__init__(message, sqlcode=DATA_SQLCODE, sqlstate=DATA_EXCEPTION)
        self.where = position
        self.cause = cause
        self.committed = committed
        self.rolled_back = rolled_back


ImportFailure.__module__ = "turborel.client"


def rows(n: int) -> str:
    """`n` rows, in words: "1 row", "2 rows"."""
    return f"{n} row{'' if n == 1 else 's'}"


def _said(cause: Cause) -> str:
    """The input's words, or an SQL condition as turborel-client writes a failure."""
    if isinstance(cause, str):
        return cause
    said = f"SQLCODE {cause.sqlcode} (SQLSTATE {cause.sqlstate}): {cause.message}"
    if cause.rule is not None:
        said += f" [{cause.rule}]"
    if cause.position is not None:
        said += f" (at character {cause.position})"
    return said


def sql(error: Error) -> Error:
    """`error`, of a statement the import made, not the user: without its position."""
    if error.failure is None or error.failure.position is None:
        return error
    return raised(dataclasses.replace(error.failure, position=None))


def _written(t: CharacterType | LobType) -> str:
    if isinstance(t, LobType):
        name = "CHARACTER LARGE OBJECT"
    else:
        name = "CHARACTER VARYING" if t.varying else "CHARACTER"
    return f"{name}({t.length} OCTETS)" if t.octets else f"{name}({t.length})"


def _count(s: str, *, octets: bool) -> int:
    return len(s.encode("utf-8")) if octets else len(s)


def _prefix(s: str, most: int, *, octets: bool) -> str:
    if not octets:
        return s[:most]
    kept, used = [], 0
    for c in s:
        used += len(c.encode("utf-8"))
        if used > most:
            break
        kept.append(c)
    return "".join(kept)


def _too_long(message: str, rule: str) -> Error:
    failure = Failure(
        sqlcode=DATA_SQLCODE,
        sqlstate=STRING_DATA_RIGHT_TRUNCATION,
        message=message,
        rule=rule,
        position=None,
        active=False,
        diagnostics=Diagnostics(severity="ERROR"),
    )
    return raised(failure)


def assign(value: str, t: CharacterType | LobType) -> str:
    """`value` assigned to a column of the character string type `t`, as INSERT assigns.

    Padded with spaces to a CHARACTER's length; cut where only spaces lie
    beyond the length.

    Raises:
        DataError: SQLSTATE 22001, if what lies beyond it is not all spaces.
    """
    count, length = _count(value, octets=t.octets), t.length
    if count <= length:
        fixed = isinstance(t, CharacterType) and not t.varying
        return value + " " * (length - count) if fixed else value
    kept = _prefix(value, length, octets=t.octets)
    if all(c == " " for c in value[len(kept) :]):
        fixed = isinstance(t, CharacterType) and not t.varying
        return kept + " " * (length - _count(kept, octets=t.octets)) if fixed else kept
    if isinstance(t, LobType):
        rule = f"{INSERT_ASSIGNS}; ISO/IEC 9075-2:2023 §9.2 GR3e ii"
        message = (
            f"a large object longer than {_written(t)},"
            " not padding beyond it, does not fit it"
        )
        raise _too_long(message, rule)
    clause = "§9.2 GR3e ii" if t.varying else "§9.2 GR3b ii"
    unit = "octets" if t.octets else "characters"
    message = (
        f"a value of {count} {unit}, not spaces beyond {length},"
        f" does not fit {_written(t)}"
    )
    raise _too_long(message, f"{INSERT_ASSIGNS}, {clause}")


def assigned(values: Sequence[object], types: Sequence[Parameter]) -> list[object]:
    """`values` as sent for parameters of `types`, strings for strings assigned."""
    out: list[object] = []
    for value, parameter in zip(values, types, strict=False):
        t = parameter.data_type
        character = isinstance(t, CharacterType) or (
            isinstance(t, LobType) and not t.binary
        )
        if isinstance(value, str) and character:
            assert isinstance(t, CharacterType | LobType)  # noqa: S101  # Just tested.
            out.append(assign(value, t))
        else:
            out.append(value)
    return out


def _is_lob(parameter: Parameter) -> bool:
    return isinstance(parameter.data_type, LobType)


def import_rows(
    connection: Bulk,
    source: Source,
    how: Import,
    rejected: Callable[[Rejected], None] | None = None,
) -> Imported:
    """Insert `source`'s records into the table `how` names, over `connection`.

    Each row skipped is given to `rejected`. The session must have no
    transaction active, as an import commits its batches.

    Raises:
        ImportFailure: Why it stopped, where, and how many rows were
            committed; the batch under way rolled back.
    """
    insert, columns = _prepared(connection, source, how)
    if (
        COPY in connection.granted
        and not how.skip
        and not any(map(_is_lob, insert.parameters))
    ):
        table = _table(how)
        types = insert.parameters
        try:
            connection.deallocate(insert)
        except Error as e:
            raise ImportFailure(None, sql(e), (0, 0)) from e
        return _Copied(connection, how, types).run(source, table, columns)
    run = _Inserted(connection, insert, how)
    try:
        done = run.rows(source, rejected or (lambda _: None))
    except ImportFailure:
        if not connection.is_lost:
            _let_go(connection, insert, None)
        raise
    _let_go(connection, insert, done)
    return done


def _let_go(connection: Bulk, insert: Statement, done: Imported | None) -> None:
    try:
        connection.deallocate(insert)
    except Error as e:
        if done is not None:
            raise ImportFailure(None, sql(e), (done.rows, 0)) from e


def _table(how: Import) -> str:
    try:
        return table_name(how.table)
    except ValueError as e:
        raise ImportFailure(None, str(e), (0, 0)) from None


def _prepared(
    connection: Bulk, source: Source, how: Import
) -> tuple[Statement, list[str]]:
    if connection.in_transaction:
        msg = "an import begins with no transaction active, as it commits its batches"
        raise ImportFailure(None, msg, (0, 0))
    table = _table(how)
    try:
        headings = source.headings()
    except SourceError as e:
        raise ImportFailure(e.where, e.reason, (0, 0)) from None
    try:
        if headings is not None:
            columns = [column_name(h.name) for h in headings]
        else:
            # The table's name delimited, so it is nothing else.
            query = connection.prepare(f"SELECT * FROM {table}")  # noqa: S608
            columns = [c.name or "" for c in query.columns]
            connection.deallocate(query)
        names = [delimited(c) for c in columns]
        marks = ", ".join("?" * len(names))
        sql_text = f"INSERT INTO {table} ({', '.join(names)}) VALUES ({marks})"  # noqa: S608
        return connection.prepare(sql_text), names
    except Error as e:
        raise ImportFailure(None, sql(e), (0, 0)) from e


class _Inserted:
    """An import by INSERT under way."""

    def __init__(self, connection: Bulk, insert: Statement, how: Import) -> None:
        self.connection = connection
        self.insert = insert
        self.how = how
        self.committed = 0
        self.in_batch = 0
        self.rejected = 0

    def rows(self, source: Source, rejected: Callable[[Rejected], None]) -> Imported:
        while True:
            try:
                record = source.record()
            except SourceError as e:
                raise self.stop(e.where, e.reason) from None
            if record is None:
                break
            self.row(record, rejected)
        self.commit()
        return Imported(self.committed, self.rejected)

    def row(self, record: Record, rejected: Callable[[Rejected], None]) -> None:
        wanted = len(self.insert.parameters)
        if len(record.values) != wanted:
            msg = f"{len(record.values)} fields, for {wanted} columns"
            self.reject(Rejected(record.position, msg), rejected)
            return
        try:
            values = self.located(assigned(record.values, self.insert.parameters))
            self.connection.execute(self.insert, values)
        except Error as e:
            # A row is skipped only if it alone was undone: the batch's
            # transaction goes on, and the connection.
            alone = self.in_batch == 0 or self.connection.in_transaction
            failure = e.failure
            ends = failure is not None and ends_connection(failure)
            if (
                not alone
                or ends
                or self.connection.is_lost
                or e.sqlcode == CANCELLED_SQLCODE
            ):
                raise self.stop(record.position, sql(e)) from e
            self.reject(Rejected(record.position, sql(e)), rejected)
            return
        self.in_batch += 1
        if self.in_batch == self.how.batch:
            self.commit()

    def located(self, values: list[object]) -> list[object]:
        """`values`, each long string for a large object sent ahead, by its locator."""
        out: list[object] = []
        for value, parameter in zip(values, self.insert.parameters, strict=False):
            t = parameter.data_type
            if not isinstance(t, LobType) or not isinstance(value, str | bytes):
                out.append(value)
                continue
            data = value.encode("utf-8") if isinstance(value, str) else value
            if len(data) <= LOB_INLINE_OCTETS:
                out.append(value)
                continue
            writer = self.connection.create_lob(binary=t.binary)
            writer.write(data)
            out.append(writer.finish())
        return out

    def reject(self, row: Rejected, rejected: Callable[[Rejected], None]) -> None:
        if not self.how.skip:
            raise self.stop(row.position, row.cause)
        self.rejected += 1
        rejected(row)

    def stop(self, position: Position | None, cause: Cause) -> ImportFailure:
        if not self.connection.is_lost and self.connection.in_transaction:
            # The import has failed already: a rollback that fails too
            # loses the connection, which ends the session's transaction.
            with contextlib.suppress(Error):
                self.connection.query("ROLLBACK")
        return ImportFailure(position, cause, (self.committed, self.in_batch))

    def commit(self) -> None:
        if self.connection.in_transaction:
            try:
                self.connection.query("COMMIT")
            except Error as e:
                raise ImportFailure(
                    None, sql(e), (self.committed, self.in_batch)
                ) from e
        self.committed += self.in_batch
        self.in_batch = 0


def _row_of(error: Error) -> int | None:
    detail = error.diagnostics.detail if error.diagnostics else None
    if (
        detail is None
        or not detail.startswith(_ROW)
        or not detail.endswith(_OF_THE_COPY)
    ):
        return None
    number = detail[len(_ROW) : -len(_OF_THE_COPY)]
    return int(number) if number.isdigit() else None


class _Copied:
    """An import by bulk copy under way: a batch to each copy, committed as it ends."""

    def __init__(
        self, connection: Bulk, how: Import, types: tuple[Parameter, ...]
    ) -> None:
        self.connection = connection
        self.how = how
        self.types = types
        self.committed = 0
        self.batch: list[Position] = []

    def run(self, source: Source, table: str, columns: list[str]) -> Imported:
        while self.copied(source, table, columns):
            pass
        return Imported(self.committed)

    def stop(
        self, position: Position | None, cause: Cause, rolled_back: int
    ) -> ImportFailure:
        return ImportFailure(position, cause, (self.committed, rolled_back))

    def checked(self, source: Source) -> tuple[Position, list[object]] | None:
        try:
            record = source.record()
        except SourceError as e:
            raise self.stop(e.where, e.reason, len(self.batch)) from None
        if record is None:
            return None
        wanted = len(self.types)
        if len(record.values) != wanted:
            msg = f"{len(record.values)} fields, for {wanted} columns"
            raise self.stop(record.position, msg, len(self.batch))
        try:
            return record.position, assigned(record.values, self.types)
        except Error as e:
            raise self.stop(record.position, sql(e), len(self.batch)) from e

    def copied(self, source: Source, table: str, columns: list[str]) -> bool:
        first = self.checked(source)
        if first is None:
            return False
        try:
            copy = self.connection._copy_begin(table, columns, ends=True)  # noqa: SLF001
        except Error as e:
            raise self.stop(None, sql(e), 0) from e
        following: tuple[Position, list[object]] | None = first
        try:
            while following is not None:
                at, values = following
                try:
                    copy.send(values)
                except Error as e:
                    raise self.stop(at, sql(e), len(self.batch)) from e
                self.batch.append(at)
                if len(self.batch) == self.how.batch:
                    self.ended(copy)
                    return True
                following = self.checked(source)
            self.ended(copy)
            return False
        finally:
            if not copy.ended and not self.connection.is_lost:
                copy.abandon()

    def ended(self, copy: Copying) -> None:
        try:
            inserted = copy.finish()
        except Error as e:
            number = _row_of(e)
            if number is not None and 0 < number <= len(self.batch):
                position: Position | None = self.batch[number - 1]
                before = number - 1
            else:
                position, before = None, len(self.batch)
            raise self.stop(position, sql(e), before) from e
        self.committed += inserted
        self.batch.clear()
