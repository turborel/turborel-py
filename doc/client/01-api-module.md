# The turborel Module

[Contents](README.md)

## NAME

`turborel`: the standard API, DB-API 2.0 (PEP 249), with `?` parameters.

## SYNOPSIS

```python
turborel.connect(dsn=None, **settings) -> Connection
turborel.apilevel == "2.0"
turborel.threadsafety == 1
turborel.paramstyle == "qmark"

Date(year, month, day) | Time(hour, minute, second)
Timestamp(year, month, day, hour, minute, second)
DateFromTicks(ticks) | TimeFromTicks(ticks) | TimestampFromTicks(ticks)
Binary(data)
STRING | BINARY | NUMBER | DATETIME | ROWID
TypeCode(data_type, name, written)
ParameterMode.IN | ParameterMode.INOUT | ParameterMode.OUT
ParameterDescription(mode, position, type_code)

Warning, Error, InterfaceError, DatabaseError, DataError, OperationalError,
IntegrityError, InternalError, ProgrammingError, NotSupportedError
```

## DESCRIPTION

**connect** connects as settings say: `dsn`, a `turborel://` URI, and
`settings`, settings by their names, laid over it, then a service's,
the environment's and the defaults ([Settings](26-settings.md));
`host`, `port`, `user`, `password`, `tls_mode` and the rest. A value of
a setting is given as text, a number or a bool. It gives a
[Connection](02-api-connection.md).

**Globals.** `apilevel` is `"2.0"`. `threadsafety` is 1: threads may
share the module, not a connection; a [pool](28-pools.md) shares
connections. `paramstyle` is `"qmark"`: a parameter is `?`, as SQL's
dynamic parameters are, so a statement goes to the server as written.

**Type objects.** A column's type code, in a cursor's `description`, is
a `TypeCode`: its `data_type`, the type its values are read by; its
declared type's `name`, as the Information Schema's DATA_TYPE gives it,
INTEGER or DECIMAL, None where the server did not tell it; and its type
as SQL `written`, which is also its string, INTEGER where it was
declared so, else as its data type says, NUMERIC(10,0). Each type object
compares equal to the type codes of its kind: `STRING` to the character string types,
CHARACTER, CHARACTER VARYING and CLOB; `BINARY` to the binary string
types, BINARY, BINARY VARYING and BLOB; `NUMBER` to the exact,
approximate and decimal floating-point types; `DATETIME` to DATE, TIME,
TIMESTAMP and the intervals; `ROWID` to a reference type.

**Parameter modes.** `ParameterMode` and `ParameterDescription` are
what a cursor's `parameters` gives after `callproc`: each `?` of the
CALL with its mode, its parameter's position and its type code
([Cursor](03-api-cursor.md)).

**Constructors.** `Date`, `Time`, `Timestamp` and `Binary` make a
`datetime.date`, `time`, `datetime`, and `bytes`; the `FromTicks`
forms read seconds since the epoch in the local time zone, as PEP 249
says. Every other value is of the Python type
[Appendix A](../appendix/a-types.md) gives.

**Exceptions.** PEP 249's, each carrying `sqlcode`, `sqlstate` and
`message`, and of a failure the server sent its `rule`, `position`,
`transaction_active` and `diagnostics` ([Errors](30-errors.md)).

## ERRORS

As [Connection](02-api-connection.md) and [Settings](26-settings.md)
give them.

## EXAMPLES

```python
import turborel

conn = turborel.connect(host="127.0.0.1", port=7422, user="ANN")
cursor = conn.cursor()
cursor.execute("VALUES (CAST(1.50 AS DECIMAL(4,2)), 'x')")
print([d[1] == turborel.NUMBER for d in cursor.description])
print(turborel.apilevel, turborel.threadsafety, turborel.paramstyle)
conn.close()
```

```text
[True, False]
2.0 1 qmark
```

## SEE ALSO

[Connection](02-api-connection.md), [Cursor](03-api-cursor.md),
[turborel.aio](04-api-aio.md).
