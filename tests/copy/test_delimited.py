"""Tests of delimited text as a source, as turborel-client's own tests read it."""

from __future__ import annotations

import io

import pytest

from turborel import InterfaceError
from turborel._codec.frames import MAX_BODY
from turborel.client import (
    DEFAULT_MAX_RECORD,
    Delimited,
    Dialect,
    Position,
    SourceError,
)


def fields(data: bytes | str, dialect: Dialect) -> list[list[object]]:
    """Each record's values, `data` read as `dialect` says."""
    raw = data.encode("utf-8") if isinstance(data, str) else data
    source = Delimited(io.BytesIO(raw), dialect)
    found = []
    while (record := source.record()) is not None:
        found.append(record.values)
    return found


def error(data: bytes, dialect: Dialect) -> SourceError:
    """The error reading `data` as `dialect` says gives."""
    source = Delimited(io.BytesIO(data), dialect)
    try:
        while source.record() is not None:
            pass
    except SourceError as e:
        return e
    pytest.fail("it was read")


def test_csv_records_and_fields() -> None:
    """Verifies: [CLIENT Importing] CSV, a header, a delimiter and a text for null.

    RFC 4180 §2: records end at CR LF or LF, the last optional; spaces
    are part of a field; quotes enclose a delimiter, a quote written
    twice, line breaks kept; an empty field null, `""` the empty string.
    """
    csv = Dialect.csv()
    assert fields("a,b\r\nc,d\n", csv) == [["a", "b"], ["c", "d"]]
    assert fields("a,b\nc,d", csv) == [["a", "b"], ["c", "d"]]
    assert fields(" a , b ", csv) == [[" a ", " b "]]
    assert fields('"a,b","say ""hi"""', csv) == [["a,b", 'say "hi"']]
    assert fields('"one\r\ntwo\nthree",x\n', csv) == [["one\r\ntwo\nthree", "x"]]
    assert fields(',"",', csv) == [[None, "", None]]
    assert fields("a\n\nb\n", csv) == [["a"], [None], ["b"]]
    assert fields('""""', csv) == [['"']]
    assert fields("", csv) == []
    assert fields("é,\U0001f600", csv) == [["é", "\U0001f600"]]


def test_csv_null_text_and_byte_order_mark() -> None:
    """Verifies: [CLIENT Importing] null's text, unquoted; a byte order mark skipped.

    Only the input's first: a later one is part of its field.
    """
    null = Dialect.csv().with_null("NULL")
    assert fields('NULL,"NULL",,null', null) == [[None, "NULL", "", "null"]]
    assert fields("﻿a,b\n﻿c", Dialect.csv()) == [["a", "b"], ["﻿c"]]


def test_csv_header_and_positions() -> None:
    """Verifies: [CLIENT Importing] headings, then records and where each began.

    The header read once, whether asked for or not; records numbered from
    the first after it, each with the line it began on; a header missing
    refused.
    """
    text = b'ID,"FULL NAME"\n1,"Ada\nLovelace"\n2,Grace\n'
    source = Delimited(io.BytesIO(text), Dialect.csv().with_header())
    headings = source.headings()
    assert headings is not None
    assert [h.name for h in headings] == ["ID", "FULL NAME"]
    assert all(h.data_type is None for h in headings)
    assert source.headings() is None
    positions = []
    while (record := source.record()) is not None:
        positions.append(record.position)
    assert positions == [Position(1, 2), Position(2, 4)]
    assert source.record() is None
    assert fields(text, Dialect.csv().with_header()) == [
        ["1", "Ada\nLovelace"],
        ["2", "Grace"],
    ]
    with pytest.raises(SourceError) as missing:
        Delimited(io.BytesIO(b""), Dialect.csv().with_header()).headings()
    assert missing.value.where == Position(0, 1)
    assert str(missing.value) == "record 0, line 1: there is no header"
    assert Delimited(io.BytesIO(b"a"), Dialect.csv()).headings() is None


def test_csv_errors_say_where() -> None:
    """Verifies: [CLIENT Importing] an input that cannot be read, said with where.

    RFC 4180 §2 rules 5 and 7: a quote in a field not quoted, more after
    a closing quote, a quote left open, a field not UTF-8; nothing more
    after.
    """
    quote = error(b'a\nb,c"d\n', Dialect.csv())
    assert quote.where == Position(2, 2)
    assert quote.reason == (
        "[RFC 4180 §2 rule 5] field 2: a quote in a field not enclosed in quotes"
    )
    after = error(b'"a"b,c', Dialect.csv())
    assert after.reason == (
        "[RFC 4180 §2 rule 5] field 1:"
        " a quoted field's closing quote is followed by more"
    )
    still_open = error(b'a\nb\n"c\nd\ne\n', Dialect.csv())
    assert still_open.where == Position(3, 3)
    assert still_open.reason == "[RFC 4180 §2 rule 5] a quoted field is not closed"
    assert error(b'"c', Dialect.csv()).reason.endswith("a quoted field is not closed")
    assert str(error(b"ok,\xff\xfe", Dialect.csv())) == (
        "record 1, line 1: field 2 is not UTF-8"
    )
    assert error(b"ok\t\xff", Dialect.tsv()).reason == "field 2 is not UTF-8"
    source = Delimited(io.BytesIO(b'"a"b\nc\n'), Dialect.csv())
    with pytest.raises(SourceError):
        source.record()
    assert source.record() is None


class _Endless(io.RawIOBase):
    def __init__(self, octet: bytes, then: bytes | None = None, count: int = 0) -> None:
        self._octet, self._then, self._count = octet, then, count

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: memoryview) -> int:  # type: ignore[override]  # bytes alike.
        for i in range(len(buffer)):
            if self._count > 0:
                self._count -= 1
                buffer[i] = self._octet[0]
            else:
                buffer[i] = (self._then or self._octet)[0]
        return len(buffer)


class _Failing(io.RawIOBase):
    def readable(self) -> bool:
        return True

    def readinto(self, _: memoryview) -> int:  # type: ignore[override]  # bytes alike.
        msg = "the disk is gone"
        raise OSError(msg)


def test_records_are_bounded() -> None:
    """Verifies: [CLIENT Importing] a record held at a time, its length bounded.

    One longer than the bound refused once the bound is read; one of the
    bound read, its line break counted; the default the protocol's
    longest body; a reader's failure told.
    """
    endless = Delimited(
        io.BufferedReader(_Endless(b"a")), Dialect.csv().with_max_record(1024)
    )
    with pytest.raises(SourceError) as long:
        endless.record()
    assert long.value.reason == "the record is longer than 1024 bytes"
    quotes = io.BufferedReader(_Endless(b'"', b"\n", 10_000))
    with pytest.raises(SourceError) as still_open:
        Delimited(quotes, Dialect.csv().with_max_record(4096)).record()
    assert still_open.value.reason == "the record is longer than 4096 bytes"
    assert fields("abcd\n", Dialect.csv().with_max_record(5)) == [["abcd"]]
    error(b"abcde\n", Dialect.csv().with_max_record(5))
    assert DEFAULT_MAX_RECORD == MAX_BODY
    failing = Delimited(io.BufferedReader(_Failing()), Dialect.csv())
    with pytest.raises(SourceError) as gone:
        failing.record()
    assert gone.value.reason == "cannot read: the disk is gone"


def test_tab_separated_records() -> None:
    """Verifies: [CLIENT Importing] tab-separated, never quoted; empty is null."""
    tsv = Dialect.tsv()
    assert fields('a\tb\r\n"c\t"d"\n', tsv) == [["a", "b"], ['"c', '"d"']]
    assert fields("a\t\tb,c", tsv) == [["a", None, "b,c"]]
    assert fields("a\t\\N", tsv.with_null("\\N")) == [["a", None]]


def test_delimiters() -> None:
    """Verifies: [CLIENT Importing] a delimiter, one ASCII character."""
    semicolon = Dialect.csv().with_delimiter(";")
    assert fields('a;"b;c";d,e', semicolon) == [["a", "b;c", "d,e"]]
    pipe = Dialect.tsv().with_delimiter("|")
    assert fields("a|b\tc", pipe) == [["a", "b\tc"]]
    for wrong in ['"', "\n", "\r", "é", "ab"]:
        with pytest.raises(InterfaceError, match="a delimiter is one ASCII character"):
            Dialect.csv().with_delimiter(wrong)
