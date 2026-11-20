"""Tests of an import's rules, over a connection of the test's own."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import pytest

from turborel import DataError, OperationalError, ProgrammingError
from turborel._codec.composites import Column, Parameter
from turborel._codec.datatypes import BooleanType, CharacterType, ExactType, LobType
from turborel._codec.failures import Diagnostics, Failure
from turborel._copy.importing import assign, assigned, sql
from turborel._session.raising import raised
from turborel._statements.prepared import Statement
from turborel.client import (
    Delimited,
    Heading,
    Import,
    Imported,
    ImportFailure,
    Position,
    Record,
    Rejected,
    SourceError,
    import_rows,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from turborel._client.bulk import Bulk

INTEGER = Parameter(varying=False, data_type=ExactType(10, 0))
CHAR_3 = CharacterType(varying=False, length=3, octets=False)
VARCHAR_3 = CharacterType(varying=True, length=3, octets=False)
OCTETS_3 = CharacterType(varying=True, length=3, octets=True)
CLOB_3 = LobType(binary=False, length=3, octets=False)


def failure(
    sqlstate: str, *, position: int | None = None, detail: str | None = None
) -> Exception:
    """The server's failure of `sqlstate`."""
    sqlcode = -919 if sqlstate.startswith("08") else -301
    found = Failure(
        sqlcode,
        sqlstate,
        "refused",
        "a rule",
        position,
        active=False,
        diagnostics=Diagnostics(detail=detail),
    )
    return raised(found)


def test_a_string_assigned_as_insert_assigns() -> None:
    """Verifies: [CLIENT Importing] a string assigned: padded, or cut of spaces.

    One whose characters past the length are not all spaces refused
    (22001), as INSERT refuses it, in characters or octets as the column
    counts; a large object's too.
    """
    assert assign("ab", CHAR_3) == "ab "
    assert assign("ab", VARCHAR_3) == "ab"
    assert assign("ab   ", CHAR_3) == "ab "
    assert assign("abc  ", VARCHAR_3) == "abc"
    assert assign("éa", OCTETS_3) == "éa"
    with pytest.raises(DataError) as long:
        assign("abcd", CHAR_3)
    assert long.value.sqlstate == "22001"
    assert long.value.message == (
        "a value of 4 characters, not spaces beyond 3, does not fit CHARACTER(3)"
    )
    assert long.value.rule == "ISO/IEC 9075:1992 §13.8 GR4b iii, §9.2 GR3b ii"
    with pytest.raises(DataError, match="a value of 4 octets, not spaces beyond 3"):
        assign("éé", OCTETS_3)
    with pytest.raises(DataError, match="does not fit CHARACTER VARYING\\(3 OCTETS\\)"):
        assign("ééé", OCTETS_3)
    with pytest.raises(DataError) as lob:
        assign("abcd", CLOB_3)
    assert lob.value.message == (
        "a large object longer than CHARACTER LARGE OBJECT(3),"
        " not padding beyond it, does not fit it"
    )
    assert assign("ab  ", CLOB_3) == "ab "
    assert assigned(
        ["x", 1, None],
        [Parameter(varying=False, data_type=VARCHAR_3), INTEGER, INTEGER],
    ) == [
        "x",
        1,
        None,
    ]


def test_an_import_s_condition_loses_its_position() -> None:
    """Verifies: [CLIENT Importing] a condition of the import's statement.

    So without its position in that statement.
    """
    placed = failure("42000", position=7)
    assert isinstance(placed, ProgrammingError)
    assert sql(placed).position is None
    unplaced = failure("42000")
    assert isinstance(unplaced, ProgrammingError)
    assert sql(unplaced) is unplaced


@dataclass
class Fake:
    """A connection that answers an import as told, keeping what it was asked."""

    granted: tuple[str, ...] = ()
    in_transaction: bool = False
    is_lost: bool = False
    columns: tuple[Column, ...] = (Column("A", ExactType(10, 0), not_null=False),)
    parameters: tuple[Parameter, ...] = (INTEGER,)
    fail_execute: dict[int, Exception] = field(default_factory=dict)
    fail_prepare: Exception | None = None
    fail_deallocate: Exception | None = None
    fail_commit: Exception | None = None
    asked: list[str] = field(default_factory=list)
    executed: int = 0

    def prepare(self, sql_text: str) -> Statement:
        """The statement `sql_text` prepares, or the failure told."""
        self.asked.append(sql_text)
        if self.fail_prepare is not None:
            raise self.fail_prepare
        query = sql_text.startswith("SELECT")
        return Statement(
            0, () if query else self.parameters, self.columns if query else ()
        )

    def deallocate(self, _: Statement) -> None:
        """Nothing, or the failure told."""
        if self.fail_deallocate is not None:
            raise self.fail_deallocate

    def execute(self, _: Statement, values: Sequence[object]) -> None:
        """A row inserted, or the failure told of it."""
        self.executed += 1
        problem = self.fail_execute.get(self.executed)
        if problem is not None:
            raise problem
        self.in_transaction = True
        self.asked.append(f"EXECUTE {list(values)}")

    def query(self, sql_text: str) -> None:
        """COMMIT or ROLLBACK, the transaction ended."""
        self.asked.append(sql_text)
        if sql_text == "COMMIT" and self.fail_commit is not None:
            raise self.fail_commit
        self.in_transaction = False


def run(
    fake: Fake, data: bytes, how: Import, rejected: list[Rejected] | None = None
) -> object:
    """An import of CSV `data` over `fake`."""
    keep = rejected.append if rejected is not None else None
    return import_rows(cast("Bulk", fake), Delimited(io.BytesIO(data)), how, keep)


def test_an_import_by_insert_in_batches() -> None:
    """Verifies: [CLIENT Importing] rows committed a batch at a time, or all at once.

    Through one prepared INSERT of the table's columns, as a prepared
    query describes them, each batch committed.
    """
    fake = Fake()
    assert run(fake, b"1\n2\n3\n", Import("T", batch=2)) == Imported(3, 0)
    assert fake.asked[:2] == ['SELECT * FROM "T"', 'INSERT INTO "T" ("A") VALUES (?)']
    assert fake.asked.count("COMMIT") == 2
    whole = Fake()
    run(whole, b"1\n2\n", Import("T", batch=0))
    assert whole.asked.count("COMMIT") == 1


def test_a_failing_row_stops_or_is_skipped() -> None:
    """Verifies: [CLIENT Importing] a failing row skipped and told, if asked.

    Only if it alone was undone; a failure that ends the connection, or a
    statement cancelled, stops the import whatever; a batch's commit that
    fails stops it, the batch rolled back.
    """
    rejected: list[Rejected] = []
    skipping = Fake(fail_execute={2: failure("22018")})
    assert run(skipping, b"1\n2\n3\n", Import("T", skip=True), rejected) == Imported(
        2, 1
    )
    assert [r.position for r in rejected] == [Position(2, 2)]
    assert str(rejected[0]).startswith(
        "record 2, line 2: SQLCODE -301 (SQLSTATE 22018): refused [a rule]"
    )
    lost = Fake(fail_execute={1: failure("08006")})
    with pytest.raises(ImportFailure) as ended:
        run(lost, b"1\n", Import("T", skip=True))
    assert ended.value.sqlstate == "08006"
    cancelled = Fake(
        fail_execute={
            1: raised(
                Failure(
                    -920,
                    "TB920",
                    "cancelled",
                    None,
                    None,
                    active=False,
                    diagnostics=None,
                )
            )
        }
    )
    with pytest.raises(ImportFailure):
        run(cancelled, b"1\n", Import("T", skip=True))
    rolled = Fake(fail_execute={2: failure("40001")})
    rolled.in_transaction = False
    with pytest.raises(ImportFailure) as undone:
        run(rolled, b"1\n2\n", Import("T", batch=5))
    assert (undone.value.committed, undone.value.rolled_back) == (0, 1)
    assert "ROLLBACK" in rolled.asked
    commit = Fake(fail_commit=failure("40001"))
    with pytest.raises(ImportFailure) as unsaved:
        run(commit, b"1\n", Import("T"))
    assert unsaved.value.rolled_back == 1


def test_an_import_that_cannot_begin() -> None:
    """Verifies: [CLIENT Importing] a failure before any row, nothing committed.

    The table not prepared, its INSERT refused, its statement not let go,
    a header that cannot be read.
    """
    for fake in (
        Fake(fail_prepare=failure("42000")),
        Fake(fail_deallocate=failure("26000")),
    ):
        with pytest.raises(ImportFailure) as stopped:
            run(fake, b"1\n", Import("T"))
        assert (stopped.value.where, stopped.value.committed) == (None, 0)
    gone = Fake(fail_deallocate=failure("26000"))
    gone.columns = ()

    class Headless:
        def headings(self) -> list[Heading] | None:
            raise SourceError(Position(0, 1), "there is no header")

        def record(self) -> Record | None:
            return None

    with pytest.raises(ImportFailure, match="there is no header") as headless:
        import_rows(cast("Bulk", Fake()), Headless(), Import("T"))
    assert headless.value.where == Position(0, 1)


def test_an_import_by_copy_ends_where_the_copy_says() -> None:
    """Verifies: [CLIENT Copying and exporting] importing by copy, where granted.

    The copy's failure at the row its detail names, `row 2 of the
    copy`, the rows before it rolled back; a record of too many fields
    refused before it is sent.
    """

    class Copy:
        def __init__(self, owner: Copier) -> None:
            self.owner, self.ended, self.sent = owner, False, 0

        def send(self, _: Sequence[object]) -> None:
            self.sent += 1

        def finish(self) -> int:
            self.ended = True
            if self.owner.refuse is not None:
                raise self.owner.refuse
            return self.sent

        def abandon(self) -> None:
            self.ended = True
            self.owner.abandoned += 1

    @dataclass
    class Copier(Fake):
        refuse: Exception | None = None
        abandoned: int = 0

        def _copy_begin(self, _: str, __: Sequence[str], *, ends: bool) -> Copy:
            assert ends
            return Copy(self)

    copier = Copier(granted=("copy",))
    assert run(copier, b"1\n2\n3\n", Import("T", batch=2)) == Imported(3, 0)
    broken = Copier(
        granted=("copy",), refuse=failure("23000", detail="row 2 of the copy")
    )
    with pytest.raises(ImportFailure) as at_row:
        run(broken, b"1\n2\n3\n", Import("T", batch=5))
    assert (at_row.value.where, at_row.value.rolled_back) == (Position(2, 2), 1)
    unnamed = Copier(granted=("copy",), refuse=failure("23000"))
    with pytest.raises(ImportFailure) as anywhere:
        run(unnamed, b"1\n", Import("T"))
    assert (anywhere.value.where, anywhere.value.rolled_back) == (None, 1)
    wide = Copier(granted=("copy",))
    with pytest.raises(ImportFailure, match="2 fields, for 1 columns"):
        run(wide, b"1\n2,3\n", Import("T"))
    assert wide.abandoned == 1
    with pytest.raises(ImportFailure, match="a quoted field is not closed"):
        run(Copier(granted=("copy",)), b'1\n"2\n', Import("T"))
    text = Copier(
        granted=("copy",), parameters=(Parameter(varying=False, data_type=CHAR_3),)
    )
    with pytest.raises(ImportFailure) as too_long:
        run(text, b"abcd\n", Import("T"))
    assert too_long.value.sqlstate == "22001"
    with pytest.raises(OperationalError):
        raise failure("08006")
    assert isinstance(BooleanType(), BooleanType)
