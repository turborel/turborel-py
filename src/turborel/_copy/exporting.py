"""Export: a query's rows written as they come [CLIENT Copying and exporting].

A query's rows are streamed from the server and written a batch at a
time, so memory holds a batch whatever the result's size. As CSV, RFC
4180: a header of the columns' names, then a record for each row, each
ended by CR LF, a field quoted where it holds a comma, a quote, a line
break or spaces at either end, a quote in it written twice; a null an
empty field, an empty string `""`. Or as the protocol's own frames: a
Description, then Rows, then a Complete, which `read_native` reads back,
every value as it was, of whatever type.
"""

from __future__ import annotations

import struct
from enum import Enum
from typing import TYPE_CHECKING, Final

from turborel._codec.frames import HEADER_BYTES, MAX_BODY, decode_header, encode_header
from turborel._codec.replies import Complete, Description, Rows, decode
from turborel._copy.text import text
from turborel._errors import connection_failure

if TYPE_CHECKING:
    from typing import BinaryIO

    from turborel._codec.composites import Column

COMPLETE: Final = ord("K")
"""The kind of a Complete frame."""
_DONE: Final = struct.pack("<iI", 0, 5) + b"00000" + b"\x00"
"""A Complete's body: SQLCODE 0, SQLSTATE 00000, no transaction, no tail."""


class ExportFormat(Enum):
    """How an export writes rows."""

    CSV = "csv"
    """CSV, RFC 4180, with a header of the columns' names."""
    NATIVE = "native"
    """The protocol's frames: a Description, Rows, a Complete."""


def csv_field(field: str) -> str:
    """`field` as CSV writes it: quoted where it must be, its quotes doubled."""
    quoted = (
        not field
        or any(c in field for c in ',"\n\r')
        or field[0].isspace()
        or field[-1].isspace()
    )
    return '"' + field.replace('"', '""') + '"' if quoted else field


def csv_record(fields: list[str]) -> bytes:
    """A CSV record of `fields`, ended by CR LF."""
    return (",".join(fields) + "\r\n").encode("utf-8")


class Writer:
    """A query's rows, written to a binary stream as they come."""

    def __init__(self, out: BinaryIO, form: ExportFormat) -> None:
        """Rows written to `out` as `form` says."""
        self._out = out
        self.form = form
        self.failed: OSError | None = None
        self._columns: tuple[Column, ...] = ()

    def write(self, data: bytes) -> None:
        """Write `data`, unless a write failed before."""
        if self.failed is None:
            try:
                self._out.write(data)
            except OSError as e:
                self.failed = e

    def frame(self, kind: int, body: bytes) -> None:
        """A frame of the server's, as read, written whole."""
        self.write(encode_header(kind, len(body)) + body)

    def columns(self, columns: tuple[Column, ...]) -> None:
        """The query's columns: CSV's header."""
        self._columns = columns
        if self.form is ExportFormat.CSV:
            self.write(csv_record([csv_field(c.name or "") for c in columns]))

    def rows(self, rows: tuple[tuple[object, ...], ...]) -> None:
        """A batch of its rows: a CSV record each."""
        if self.form is not ExportFormat.CSV:
            return
        types = [c.data_type for c in self._columns]
        records = b"".join(
            csv_record(
                [
                    ""
                    if v is None
                    else csv_field(text(v, types[i] if i < len(types) else None))
                    for i, v in enumerate(row)
                ]
            )
            for row in rows
        )
        self.write(records)

    def finish(self) -> None:
        """End the export: a native one's Complete, then a flush.

        Raises:
            OperationalError: SQLSTATE 08006, of the export, not the
                connection, if a write to its stream failed.
        """
        if self.form is ExportFormat.NATIVE:
            self.frame(COMPLETE, _DONE)
        if self.failed is None:
            try:
                self._out.flush()
            except OSError as e:
                self.failed = e
        if self.failed is not None:
            msg = f"cannot write the export: {self.failed}"
            raise connection_failure(msg) from self.failed


def read_native(data: BinaryIO) -> tuple[tuple[Column, ...], list[tuple[object, ...]]]:
    """Native rows read back from `data`: the columns, and the rows.

    Raises:
        OperationalError: SQLSTATE 08006, of input that is not native rows,
            or cut short.
    """

    def next_reply() -> object:
        head = data.read(HEADER_BYTES)
        if len(head) != HEADER_BYTES:
            msg = "not native rows: the input ends within a frame"
            raise connection_failure(msg)
        kind, length = decode_header(head, MAX_BODY)
        body = data.read(length)
        if len(body) != length:
            msg = "not native rows: the input ends within a frame"
            raise connection_failure(msg)
        return decode(kind, body)

    first = next_reply()
    if not isinstance(first, Description):
        msg = "not native rows: no Description first"
        raise connection_failure(msg)
    rows: list[tuple[object, ...]] = []
    while True:
        reply = next_reply()
        if isinstance(reply, Rows):
            rows.extend(reply.rows)
        elif isinstance(reply, Complete):
            return first.columns, rows
        else:
            msg = "not native rows: a frame other than Rows before the Complete"
            raise connection_failure(msg)
