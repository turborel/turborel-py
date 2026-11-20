# Errors and Diagnostics

[Contents](README.md)

A statement that fails raises one of PEP 249's exceptions, which the
module `turborel` holds. Each carries the SQLCODE and SQLSTATE the
server gave, so a program decides by the SQLSTATE rather than by the
exception's class alone. A statement that succeeds may still warn.

## A failure

The exception's class follows its SQLSTATE's class: a data exception,
of class 22, is a `DataError`; an integrity constraint violated, of
class 23, an `IntegrityError`; a syntax error or a table not defined, a
`ProgrammingError`; a connection failure, an `OperationalError`;
[Appendix B](../appendix/b-errors.md) gives every class. Each is a
`turborel.Error`, and each but `InterfaceError` a `DatabaseError`.

```python
from turborel import ProgrammingError
from turborel.client import Trust, connect

conn = connect(("127.0.0.1", 7422), "ANN", Trust())
try:
    conn.query("SELECT NAME FROM NOWHERE")
except ProgrammingError as e:
    print(e.sqlcode, e.sqlstate)
    print(e.message)
    print(e.rule, e.position, e.transaction_active)
```

```text
-103 2A000
table ANN.NOWHERE is not defined
X3.135-1986 §5.4 SR5 17 True
```

| Member | What |
|---|---|
| `sqlcode`, `sqlstate`, `message` | the failure's SQLCODE, SQLSTATE and message |
| `rule` | the rule of the standard, or of Turborel's design, that the failure cites, apart from the message |
| `position` | where in the SQL text the failure lies: the characters before it |
| `transaction_active` | whether the session's transaction is still active after it |
| `diagnostics` | what more the server told of it, with `diagnostics` |
| `failure` | the failure whole, as the server sent it |

A failure the driver raises itself, such as a value it cannot send, has
no rule, position or diagnostics.

## Diagnostics

With the capability `diagnostics`, granted by default, a failure tells
its severity and what it is about: a detail, a hint, its context, and
the schema, table, column, data type and constraint it concerns, each
where the failure has one.

```python
from turborel import IntegrityError

conn.query("CREATE TABLE KEYS (ID INTEGER CONSTRAINT KEYS_ID PRIMARY KEY)")
conn.query("INSERT INTO KEYS VALUES (1)")
conn.query("COMMIT")
try:
    conn.query("INSERT INTO KEYS VALUES (1)")
except IntegrityError as e:
    told = e.diagnostics
    print(told.severity, told.table, told.constraint)
    print(told.detail)
conn.query("ROLLBACK")
```

```text
ERROR KEYS KEYS_ID
the key (1) is held by another row
```

## Failures that end the connection

A connection exception, of SQLSTATE class 08 but 08003, ends the
connection, as do credentials refused as it is made, and any failure of
its stream: a server gone, a read that waits past its timeout, a reply
that cannot be read. The connection is then lost, `is_lost` is true,
and every later call raises the same failure again. A method that needs
a capability the server did not grant fails with SQLSTATE 08006 before
it sends anything, and the connection goes on.

## Warnings, notices and conditions

A statement that succeeds with a warning completes with an SQLSTATE of
class 01, which `warning` gives. Each condition it raised, a warning or
a note, comes one way: in its completion, with the capability
`conditions`, which `conditions` then gives; else as a notice, with
`notices`; else not at all. A failing statement's conditions come as
notices. The server's own notices, such as 01T01 when a reset rolls a
transaction back, always come as notices.

A connection keeps the last 64 notices for `take_notices`, or gives each
to a handler as it comes:

```python
heard = []
conn.set_notice_handler(heard.append)
conn.query("INSERT INTO KEYS VALUES (2)")
conn.reset()
print([(n.sqlstate, n.message) for n in heard])
```

```text
[('01T01', '[DESIGN] Reset rolled back the transaction that was active')]
```

## See also

[Errors](../client/30-errors.md), the reference page;
[Appendix B: Errors](../appendix/b-errors.md).
