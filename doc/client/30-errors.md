# Errors

[Contents](README.md)

## NAME

`turborel.Error` and its subclasses: the driver's error, a failure of
the server's or of its own.

## SYNOPSIS

```python
class Warning(Exception), class Error(Exception)
    message: str
    sqlcode: int
    sqlstate: str
    failure: Failure | None
    rule: str | None
    position: int | None
    transaction_active: bool | None
    diagnostics: Diagnostics | None

InterfaceError(Error)
DatabaseError(Error)
    DataError, OperationalError, IntegrityError,
    InternalError, ProgrammingError, NotSupportedError
```

## DESCRIPTION

The exceptions are PEP 249's, in the module `turborel`, and the
low-level client raises the same. Each carries the condition's
`sqlcode`, `sqlstate` and `message`, as the server gave them or as the
driver gives its own.

**Its class.** A failure of the server's is raised as the class its
SQLSTATE's class takes, [Appendix B](../appendix/b-errors.md) giving
each. A program that must tell one failure from another reads its
SQLSTATE: a class holds failures of many kinds.

**What the server told.** `failure` is the failure whole, as the server
sent it, and None of one the driver raised itself. From it come:
`rule`, the rule of the standard or of Turborel's design the failure
cites, apart from its message; `position`, the characters before the
point of the SQL text where it lies; `transaction_active`, whether the
session's transaction is active after it; and, with `diagnostics`,
`diagnostics`, a `Diagnostics` of its `severity`, `detail`, `hint`,
`context`, `schema`, `table`, `column`, `data_type` and `constraint`,
each None where the failure has none. Each is None where the server did
not tell it.

**A lost connection.** A failure of class 08 but 08003, credentials
refused as the connection is made, or a failure of the stream loses the
connection: every later call raises the same exception again, and
`is_lost` is true.

**Warnings.** A warning is not raised: a statement that completes with
one gives its SQLSTATE as `warning`, and its conditions as `conditions`
or as notices ([Statements and Cursors](22-statements.md)). PEP 249's
`Warning`, which carries the same members, is in the module for
programs that name it.

## ERRORS

The failures the driver raises itself:

| Condition | Class | SQLCODE, SQLSTATE |
|---|---|---|
| A server that cannot be reached, a TLS handshake that fails, a wait that runs out, a reply malformed, out of turn or too long | `OperationalError` | -919, 08006 |
| A reply holding a value the driver cannot take, its statement's other replies read past and the connection kept ([Values](23-values.md)) | `OperationalError` | -916, TB916 |
| A method needing a capability the server did not grant, before it sends anything | `OperationalError` | -919, 08006 |
| A password, or SCRAM, over plain TCP, before connecting | `OperationalError` | -919, 28000 |
| A value of a type the protocol cannot carry | `DataError` | -301, 22000 |
| A number its field cannot hold, or not finite | `DataError` | -301, 22003 |
| A datetime its fields cannot hold | `DataError` | -301, 22008 |
| An XML value whose nodes are asked for, not well-formed or declaring a document type | `DataError` | -301, 2200M |
| A value past the protocol's limits: nested deeper than 16, a multiset of more than 65 535 elements, a JSON value past 128 levels or 256 MiB, sent or received | `NotSupportedError` | -900, 0A000 |
| A large object held whole freed or held as if by its locator | `DataError` | -301, 22000 |
| An import's input that cannot be read ([Copy, Import and Export](25-copy.md)) | `ImportFailure` | -301, 22000 |
| Attributes past their bounds: more than 32, a name not 1 to 64 bytes, a value past 1024, before anything is sent | `OperationalError` | -919, 08006 |
| An interface used wrongly: a field given a number it cannot hold, a request while a copy is under way | `InterfaceError` | -910, TB910 |

## EXAMPLES

```python
from turborel import DataError
from turborel.client import Trust, connect

conn = connect(("127.0.0.1", 7422), "ANN", Trust())
try:
    conn.query("VALUES 1 / 0")
except DataError as e:
    print(e.sqlcode, e.sqlstate, e.message, e.rule)
```

```text
-301 22012 a divisor shall not be 0 X3.135-1986 §5.9 GR5
```

## SEE ALSO

[Errors and Diagnostics](../user/10-errors.md),
[Appendix B: Errors](../appendix/b-errors.md),
[The turborel Module](01-api-module.md).
