"""Bulk copy into a table, as steps without I/O [CLIENT Copying and exporting].

[PROTOCOL CopyIn 'I'] begins a copy, naming the table and its columns;
[PROTOCOL CopyData 'J'] sends rows, many to a message, each with no
reply, or with `columns` [PROTOCOL CopyColumns 'O'] rows of text by
column; [PROTOCOL CopyEnd 'N'] ends it, its reply the rows inserted or
the copy's failure, every row of it undone. Until CopyEnd only CopyData,
CopyColumns, CopyEnd and Ping are sent. The server assigns each value to its column
as INSERT does, so a string too long for its column is refused, not cut.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from turborel._codec import requests
from turborel._codec.replies import Complete, Error
from turborel._session.capabilities import COPY
from turborel._session.ops import Send, receive

if TYPE_CHECKING:
    from collections.abc import Sequence

    from turborel._session.ops import Steps
    from turborel._session.state import Session

CHUNK_BYTES: Final = 256 * 1024
"""The octets of rows a CopyData carries at most, about: enough that a
message's cost is shared by many rows, few enough that neither side
holds much."""


def begin(
    session: Session, table: str, columns: Sequence[str], *, ends: bool
) -> Steps[None]:
    """A copy into `table`'s `columns` begun, ending its transaction if `ends`."""
    session.needs(COPY)
    yield Send(requests.CopyIn(table, tuple(columns), ends).encode())


def data(rows: Sequence[bytes]) -> Steps[None]:
    """Rows sent, each as `encoded_row` gave it; no reply."""
    yield Send(requests.copy_data(rows))


def by_column(rows: Sequence[Sequence[str | None]], width: int) -> Steps[None]:
    """Rows of text cells sent by column, in a CopyColumns; no reply."""
    yield Send(requests.CopyColumns(rows, width).encode())


def end(session: Session, *, abandon: bool) -> Steps[int]:
    """The copy ended, or abandoned: the rows inserted."""
    yield Send(requests.CopyEnd(abandon).encode())
    reply = yield from receive(session)
    if isinstance(reply, Complete):
        return reply.rows or 0
    if isinstance(reply, Error):
        raise session.failed(reply.failure)
    raise session.lose_by("the server sent no completion")
