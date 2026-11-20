"""What a cursor keeps of an outcome, shared by the blocking and the asyncio cursor.

A query's columns become PEP 249's `description`, seven items each:
its name, its type code (a `TypeCode`, the type as declared where the
server told it), a display size, an internal size, a precision,
a scale, and whether it may be null. Its rows are kept, and fetched from
in order. Another statement's completion gives `rowcount`, the rows it
changed where the server told it, else -1.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from turborel._api.types import TypeCode
from turborel._codec.datatypes import BinaryType, CharacterType, ExactType, LobType
from turborel._errors import misuse
from turborel._statements.queries import Rowset

if TYPE_CHECKING:
    from collections.abc import Sequence

    from turborel._codec.composites import Column
    from turborel._statements.queries import Outcome

ARRAYSIZE: Final = 1
"""How many rows `fetchmany` gives by default, as PEP 249 says."""

Description = tuple[str, TypeCode, int | None, int | None, int | None, int | None, bool]
"""A column as PEP 249 describes it."""


def described(column: Column) -> Description:
    """`column` as PEP 249 describes it."""
    t = column.data_type
    internal = t.length if isinstance(t, CharacterType | BinaryType | LobType) else None
    precision, scale = (
        (t.precision, t.scale) if isinstance(t, ExactType) else (None, None)
    )
    code = TypeCode.of(column)
    return (
        column.name or "",
        code,
        None,
        internal,
        precision,
        scale,
        not column.not_null,
    )


@dataclass(slots=True)
class Results:
    """A cursor's outcome: description, rows, row count, and where its fetch is."""

    description: tuple[Description, ...] | None = None
    rows: list[tuple[object, ...]] = field(default_factory=list)
    rowcount: int = -1
    at: int = 0
    queried: bool = False

    def take(self, outcome: Outcome) -> None:
        """Keep `outcome`, a query's rows or another statement's completion."""
        self.at = 0
        if isinstance(outcome, Rowset):
            self.description = tuple(described(c) for c in outcome.columns)
            self.rows = outcome.rows
            self.rowcount = len(outcome.rows)
            self.queried = True
        else:
            self.description, self.rows, self.queried = None, [], False
            self.rowcount = -1 if outcome.rows is None else outcome.rows

    def counted(self, outcomes: Sequence[Outcome]) -> None:
        """Keep the completions of an `executemany`: the rows they changed, all told."""
        self.description, self.rows, self.queried, self.at = None, [], False, 0
        told = [getattr(o, "rows", None) for o in outcomes]
        self.rowcount = (
            -1 if any(n is None for n in told) else sum(n or 0 for n in told)
        )

    def fetch(self, size: int | None) -> list[tuple[object, ...]]:
        """The next `size` rows, all the rest if None.

        Raises:
            InterfaceError: SQLSTATE TB910, if no query was executed.
        """
        if not self.queried:
            msg = "the cursor's last statement was no query: it has no rows to fetch"
            raise misuse(msg)
        end = (
            len(self.rows)
            if size is None
            else min(self.at + max(size, 0), len(self.rows))
        )
        taken = self.rows[self.at : end]
        self.at = end
        return taken

    def fetchone(self) -> tuple[object, ...] | None:
        """The next row, or None at the end."""
        found = self.fetch(1)
        return found[0] if found else None


def parameters_of(parameters: Sequence[object] | None) -> tuple[object, ...] | None:
    """The values of `parameters`, as `qmark` takes them, by position; None of none.

    Raises:
        InterfaceError: SQLSTATE TB910, of a mapping, which `qmark` has no
            names for.
    """
    if parameters is None:
        return None
    if isinstance(parameters, dict | str | bytes):
        msg = "parameters are a sequence, a value for each ? in order (qmark)"
        raise misuse(msg)
    return tuple(parameters)
