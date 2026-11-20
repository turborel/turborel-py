# Values

[Contents](README.md)

## NAME

The values a program reads and sends, one for each of the native
protocol's value tags.

## DESCRIPTION

A value read from the server reaches a program as the Python type
[Appendix A](../appendix/a-types.md) lists: `str`, `int` or
`decimal.Decimal`, `float`, `bytes`, `bool`, `datetime.date`,
`datetime.time` and `datetime.datetime`, `list` for an array, `tuple`
for a row, `uuid.UUID`, and a JSON value as its JSON value. A program
sends a parameter of those types, and the driver writes each under its
tag.

Where Python has no type of its own, or where its type alone would be
sent as another, the module `turborel` has a class:

| Class | Holds | Read | Sent |
|---|---|---|---|
| `DecFloat(value)` | a `Decimal` sent as DECFLOAT | no; a DECFLOAT is read as a `Decimal` | yes |
| `Interval(qualifier, units)` | a `Qualifier(start, end, leading_precision, fractional_precision)` of `IntervalField` members, and months or microseconds | yes | yes |
| `Json(value)` | a JSON value to send | no; JSON is read as its value | yes |
| `Xml(text)` | an XML value's serialization as CONTENT | yes | yes |
| `Multiset(elements)` | a multiset's elements, a tuple | yes | yes |
| `Structured(schema, name, attributes)` | a structured value of its most specific type | yes | yes |
| `Reference(octets)` | a reference | yes | yes |
| `LargeObject(data)` | a CLOB's `str` or a BLOB's `bytes`, sent whole | no; one held whole is read as `str` or `bytes` | yes |
| `LobLocator(binary, locator, octets, characters)` | a large object by its locator | yes | yes |
| `PluginValue(type_name, text, data)` | a plug-in's value, sent back unchanged | yes | yes |

Each class is frozen: it compares and hashes by its value.

## ERRORS

A value that cannot be sent is refused before anything is sent, so the
server never sees it: of a Python type no value carries,
`DataError`, SQLSTATE 22000; a number past its fields,
`DataError`, SQLSTATE 22003; a displacement of part of a minute,
SQLSTATE 22008; parts nested past 16 levels, a multiset of more than
65 535 elements or a JSON value past 128 levels or 256 MiB,
`NotSupportedError`, SQLSTATE 0A000.

A value the server sends that cannot be read fails the connection,
`OperationalError`, SQLCODE -919 and SQLSTATE 08006, as does a datetime
past Python's years 1 to 9999.

## SEE ALSO

[Appendix A: Types](../appendix/a-types.md), the bounds of each value;
[Statements and Cursors](22-statements.md), where values are read and
sent.
