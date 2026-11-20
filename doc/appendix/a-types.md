# Appendix A: Types

[Contents](README.md)

Every value of the native protocol reaches a Python program as the type
below, and a program sends a value of that type for a parameter. Where
Python has no type of its own, or where its type alone would be sent as
another, the driver has a class of its own, from the module `turborel`.
The value's tag is the one the server writes it with
([The Native Protocol](https://github.com/turborel/turborel/blob/main/doc/client/05-protocol.md)),
which is not always its column's type's: a CHARACTER VARYING value comes
with tag 1, as a CHARACTER value does.

## Values

| Tag | Value | Read as | Sent from |
|---|---|---|---|
| 0 | null | `None` | `None` |
| 1 | character string | `str` | `str` |
| 2 | exact number | `int` of scale 0, else `decimal.Decimal` | `int`, `decimal.Decimal` |
| 3 | approximate number | `float` | `float` |
| 4 | a plug-in's value | `turborel.PluginValue` | `turborel.PluginValue` |
| 6 | binary string | `bytes` | `bytes`, `bytearray`, `memoryview` |
| 8 | date | `datetime.date` | `datetime.date` |
| 9 | time | `datetime.time` | `datetime.time` |
| 11 | timestamp | `datetime.datetime` | `datetime.datetime` |
| 13 | interval | `turborel.Interval` | `turborel.Interval` |
| 14 | truth value | `bool` | `bool` |
| 15 | decimal floating point | `decimal.Decimal` | `turborel.DecFloat` |
| 16 | array | `list` | `list` |
| 17 | row | `tuple` | `tuple` |
| 20 | large object, whole | `str` of a CLOB, `bytes` of a BLOB | `turborel.LargeObject` |
| 21 | large object, by locator | `turborel.LobLocator` | `turborel.LobLocator` |
| 22 | multiset | `turborel.Multiset` | `turborel.Multiset` |
| 23 | structured value | `turborel.Structured` | `turborel.Structured` |
| 24 | reference | `turborel.Reference` | `turborel.Reference` |
| 25 | JSON | its JSON value: `None`, `bool`, `int`, `decimal.Decimal`, `float`, `str`, a datetime, `list` or `dict` | `turborel.Json` |
| 26 | XML | `turborel.Xml` | `turborel.Xml` |
| 27 | UUID | `uuid.UUID` | `uuid.UUID` |

A value sent of any other Python type is refused before anything is
sent, with `turborel.ProgrammingError`, SQLSTATE 07006.

## The bounds of each

**Exact numbers.** An exact number is its units, from -2^127 to
2^127 - 1, divided by ten to its scale, from 0 to 4 294 967 295. One of
scale 0 is an `int`; another a `Decimal` whose exponent is minus its
scale, so 1.50 keeps its two places. Neither passes through a `float`.
An `int` or `Decimal` sent past those bounds, or not finite, is refused
with `turborel.DataError`, SQLSTATE 22003.

**DECFLOAT.** A DECFLOAT has at most 34 digits and an adjusted exponent
from -6143 to 6144, with no trailing zero. It is read as a `Decimal`. To
send one, wrap a `Decimal` in `turborel.DecFloat`; one of more digits,
or past those exponents, is refused with SQLSTATE 22003.

**Approximate numbers.** A `float` is the double it was, NaN and -0.0
among them.

**Datetimes.** A date, a time and a timestamp keep microseconds, as
Python does. A time or a timestamp WITH TIME ZONE is read with a fixed
`datetime.timezone` of its displacement, from -12:59 to +14:00; one
without a zone is naive, in the displacement the server shows it in. An
aware `datetime` or `time` is sent WITH TIME ZONE, a naive one without;
its displacement must be whole minutes (else SQLSTATE 22008), and a
`time`'s zone must give one without a date (else SQLSTATE 07006). The
driver sends a time or a timestamp with 6 digits of the second's
fraction. A value past Python's years 1 to 9999 cannot be read.

**Intervals.** `turborel.Interval` holds the interval's qualifier, a
`turborel.Qualifier` of its start and end fields, `IntervalField.YEAR`
to `IntervalField.SECOND`, and its leading and fractional precisions;
and its units, months of a year-month interval, microseconds of a
day-time one, from -2^127 to 2^127 - 1.

**Arrays, rows, multisets and structured values.** These nest at most
16 deep, and a multiset holds at most 65 535 elements; more is refused
with `turborel.NotSupportedError`, SQLSTATE 0A000.

**Large objects.** A CLOB or a BLOB short enough comes whole, as `str`
or `bytes`; a longer one as a `turborel.LobLocator`: its kind, its
locator, its octets and its characters. `turborel.LargeObject` sends a
`str` as a CLOB and `bytes` as a BLOB, whole.

**JSON.** A JSON value comes as its JSON value. An object is a `dict` in
the order its members were written; of members of one key, the first is
kept, as Turborel's member accessor takes it. A number is an `int`, a
`Decimal` or a `float` as Turborel holds it, a DECFLOAT among them as a
`Decimal`, and a datetime as above. To send one, wrap it in
`turborel.Json`: its objects' keys are `str`, it nests at most 128 deep,
and it takes at most 256 MiB.

**UUIDs.** A UUID is its 16 octets, a `uuid.UUID`.

**A plug-in's value.** `turborel.PluginValue` holds its type's name, its
text and its bytes, and goes back to the server unchanged.

## Data types

Columns and parameters describe their values by a data type, one of the
protocol's tags 1 to 27: CHARACTER and CHARACTER VARYING with a length
in characters or octets; exact and approximate numeric with their
precision and scale; a plug-in's type by its name and parameters;
BINARY and BINARY VARYING; DATE, TIME and TIMESTAMP, with or without a
time zone, with their precision; INTERVAL with its qualifier; BOOLEAN;
DECFLOAT; arrays, rows and multisets of their element and field types;
CLOB and BLOB with their length; structured and reference types by
their names; JSON; XML with its modifiers; and UUID. A distinct type is
described as its source type. How a program reads a column's type is
told with the statements, at milestone M3.
