"""Fuzz and property tests of the codec, from a fixed seed.

Every case comes from `random.Random` seeded with a constant, so each run
makes the same cases (R-TEST-5): replies damaged byte by byte, which
the decoder either reads or refuses as a connection failure, never with
another exception; and values made at random, which read back as
written.
"""

from __future__ import annotations

import datetime as dt
import random
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Final

import pytest

from turborel import NotSupportedError, OperationalError
from turborel._codec import compress, jsontree, jsonwrite, replies
from turborel._codec.datatypes import read_data_type
from turborel._codec.fields import I128_MAX, I128_MIN, Reader, Writer
from turborel._codec.values import read_row, read_value, write_row
from turborel._values import Json, Multiset, Structured

if TYPE_CHECKING:
    from collections.abc import Callable

SEED = 20261119
CASES = 3000


def u32(n: int) -> bytes:
    """A `u32`, little-endian."""
    return n.to_bytes(4, "little")


def text(s: str) -> bytes:
    """A string: its length, then its UTF-8."""
    return u32(len(s.encode())) + s.encode()


def row_body(values: list[object]) -> bytes:
    """A Rows reply's body of one row of `values`."""
    w = Writer()
    write_row(w, values)
    return u32(1) + w.data()


FAILURE = (
    u32(0xFFFF_FF99)
    + text("2A000")
    + text("m")
    + b"\x01"
    + text("r")
    + b"\x01"
    + bytes(8)
    + b"\x00"
)

# Replies of every kind, each of them valid, to damage.
CORPUS = [
    (ord("B"), row_body([1, "é", Decimal("-1.50"), 0.5, b"\x00", True, None])),
    (
        ord("B"),
        row_body(
            [
                dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
                dt.date(2024, 2, 29),
                dt.time(1, 2),
            ]
        ),
    ),
    (
        ord("B"),
        row_body([[1, [2]], ("x",), Multiset((1,)), Structured("S", "T", (1,))]),
    ),
    (
        ord("B"),
        row_body([Json({"a": [1, "b", None, 1.5, Decimal("2.5")]}), uuid.UUID(int=7)]),
    ),
    (
        ord("K"),
        u32(0)
        + text("00000")
        + b"\x01\x04"
        + bytes(8)
        + b"\x05\x06"
        + bytes(8)
        + b"\x11"
        + u32(1)
        + u32(len(FAILURE))
        + FAILURE,
    ),
    (ord("E"), FAILURE + b"\x07" + text("ERROR") + b"\x0f" + text("PK")),
    (
        ord("R"),
        text("ANN")
        + bytes(16)
        + u32(1)
        + text("ping")
        + text("turborel 0.0.0 (alpha)"),
    ),
    (
        ord("P"),
        u32(1)
        + u32(1)
        + b"\x00\x02"
        + u32(5)
        + u32(2)
        + u32(1)
        + b"\x01"
        + text("K")
        + b"\x10"
        + u32(3)
        + b"\x0e"
        + b"\x00",
    ),
    (
        ord("D"),
        u32(1)
        + b"\x00\x1a\x00\x02"
        + text("A")
        + text("S")
        + b"\x01"
        + text("urn")
        + b"\x00"
        + b"\x00",
    ),
    (ord("N"), text("01000") + text("w") + b"\x07" + text("WARNING")),
    (ord("L"), b"\x00" + u32(3) + b"abc"),
    (ord("T"), text("SCHEMA") + text("ANN")),
]


def outcome(call: Callable[[], object]) -> OperationalError | NotSupportedError | None:
    """The failure `call` raises, or None if it reads."""
    try:
        call()
    except (OperationalError, NotSupportedError) as e:
        return e
    return None


REFUSALS: Final = {(-919, "08006"), (-916, "TB916"), (-900, "0A000")}
"""A frame malformed, a value the client cannot take, or one past the limits."""


def damaged(rng: random.Random, body: bytes) -> bytes:
    """`body` damaged one way, as a peer or the network might."""
    data = bytearray(body)
    way = rng.randrange(4)
    if way == 0 and data:
        data[rng.randrange(len(data))] = rng.randrange(256)
    elif way == 1:
        del data[rng.randrange(len(data) + 1) :]
    elif way == 2:
        at = rng.randrange(len(data) + 1)
        data[at:at] = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 5)))
    else:
        data = bytearray(rng.randrange(256) for _ in range(rng.randrange(40)))
    return bytes(data)


def test_a_damaged_reply_is_read_or_fails_the_connection() -> None:
    """Verifies: [PROTOCOL Errors and notices] a malformed message fails the connection.

    Of 3000 replies damaged from a fixed seed, each is read or refused:
    as malformed, SQLCODE -919 and SQLSTATE 08006; or of a value the client
    cannot take, -916 and TB916, or past a limit, -900 and 0A000
    [PROTOCOL Values and fields]; and no other exception reaches the
    caller (RULES.md R-ERR-1, R-SAFE-1).
    """
    rng = random.Random(SEED)
    refused = 0
    for _ in range(CASES):
        kind, body = rng.choice(CORPUS)
        if rng.randrange(10) == 0:
            kind = rng.randrange(256)
        body = damaged(rng, body)
        error = outcome(lambda: replies.decode(kind, body))  # noqa: B023  # Called at once.
        if error is not None:
            assert (error.sqlcode, error.sqlstate) in REFUSALS
            refused += 1
    assert 0 < refused < CASES


def _value(data: bytes) -> object:
    return read_value(Reader(data, "reply"))


def _data_type(data: bytes) -> object:
    return read_data_type(Reader(data, "reply"))


def _json(data: bytes) -> object:
    r = Reader(b"", "reply")
    return jsontree.decode(data, r.damaged, r.beyond)


@pytest.mark.parametrize(
    "read",
    [_value, _data_type, _json, compress.decompress],
    ids=["value", "data type", "JSON", "z frame"],
)
def test_bytes_at_random_never_raise_another_exception(
    read: Callable[[bytes], object],
) -> None:
    """Verifies: [DESIGN] D13 a value, a type, a JSON value or a `z` frame at random.

    Each is read, or refused as malformed or as a value refused, and
    nothing else.
    """
    rng = random.Random(SEED)
    for _ in range(CASES):
        data = bytes(rng.randrange(256) for _ in range(rng.randrange(1, 48)))
        if rng.randrange(2):
            data = bytes([rng.choice((1, 16, 17, 22, 23, 25, 26))]) + data
        error = outcome(lambda: read(data))  # noqa: B023  # Called at once.
        assert error is None or (error.sqlcode, error.sqlstate) in REFUSALS


def _decimal(rng: random.Random) -> Decimal:
    digits = tuple(rng.randrange(10) for _ in range(rng.randrange(1, 30)))
    return Decimal((rng.randrange(2), digits, -rng.randrange(40)))


def _text(rng: random.Random) -> str:
    return "".join(chr(rng.randrange(0x20, 0x2FFF)) for _ in range(rng.randrange(8)))


def _timestamp(rng: random.Random) -> dt.datetime:
    start = dt.datetime(1, 1, 1)  # noqa: DTZ001  # turborel's epoch.
    return start + dt.timedelta(microseconds=rng.randrange(315_537_897_600_000_000))


# Each kind of leaf value, made at random.
LEAVES: list[Callable[[random.Random], object]] = [
    lambda _: None,
    lambda rng: rng.randrange(I128_MIN, I128_MAX),
    _decimal,
    lambda rng: rng.uniform(-1e300, 1e300),
    _text,
    lambda rng: bytes(rng.randrange(256) for _ in range(rng.randrange(8))),
    lambda rng: rng.randrange(2) == 1,
    _timestamp,
]


def made(rng: random.Random, depth: int) -> object:
    """A value made at random, its parts at most 3 deep."""
    kind = rng.randrange(len(LEAVES) + (0 if depth >= 3 else 2))
    if kind < len(LEAVES):
        return LEAVES[kind](rng)
    parts = [made(rng, depth + 1) for _ in range(rng.randrange(4))]
    return parts if kind == len(LEAVES) else tuple(parts)


def test_values_made_at_random_read_back_as_written() -> None:
    """Verifies: [PROTOCOL Values] 3000 rows of values, read back as written.

    Exact numbers over the whole `i128` range, scales to 39, doubles,
    strings, binary strings, truth values, timestamps over years 1 to
    9999, arrays and rows of them.
    """
    rng = random.Random(SEED)
    for _ in range(CASES):
        row = [made(rng, 0) for _ in range(rng.randrange(1, 5))]
        w = Writer()
        write_row(w, row)
        assert read_row(Reader(w.data(), "reply")) == tuple(row)


def json_made(rng: random.Random, depth: int) -> object:
    """A JSON value made at random, at most 3 deep."""
    kind = rng.randrange(6 if depth >= 3 else 8)
    leaves = [
        None,
        rng.randrange(2) == 1,
        rng.randrange(-(1 << 100), 1 << 100),
        Decimal(rng.randrange(-(10**20), 10**20)).scaleb(-rng.randrange(300)),
        rng.uniform(-1e10, 1e10),
        "".join(chr(rng.randrange(0x20, 0x7F)) for _ in range(rng.randrange(6))),
    ]
    if kind < len(leaves):
        return leaves[kind]
    if kind == len(leaves):
        return [json_made(rng, depth + 1) for _ in range(rng.randrange(4))]
    keys = (
        "".join(chr(rng.randrange(0x61, 0x65)) for _ in range(2))
        for _ in range(rng.randrange(4))
    )
    return {key: json_made(rng, depth + 1) for key in keys}


def test_json_values_made_at_random_read_back_as_written() -> None:
    """Verifies: [PROTOCOL Values] 3000 JSON values through D89's tree and back."""
    rng = random.Random(SEED)
    fail = Reader(b"", "reply").malformed
    for _ in range(CASES):
        value = json_made(rng, 0)
        assert jsontree.decode(jsonwrite.encode(value), fail) == value
