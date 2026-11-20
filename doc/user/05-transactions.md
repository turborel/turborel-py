# Transactions

[Contents](README.md)

Every statement runs within a transaction. A session's transaction
begins with its first statement and lasts until the program commits or
rolls it back; under autocommit, each statement is a transaction of its
own. This chapter uses the low-level client, `turborel.client`.

## COMMIT and ROLLBACK

A program ends its transaction with the statements COMMIT and ROLLBACK.
`in_transaction` says whether a transaction is active, as the server
said after the last statement.

```python
from turborel.client import Trust, connect

conn = connect(("127.0.0.1", 7422), "ANN", Trust())
conn.query("CREATE TABLE ACCOUNTS (ID INTEGER PRIMARY KEY, BALANCE INTEGER)")
print(conn.in_transaction)
conn.query("COMMIT")
print(conn.in_transaction)
conn.query("INSERT INTO ACCOUNTS VALUES (1, 100)")
conn.query("ROLLBACK")
print(conn.query("SELECT COUNT(*) FROM ACCOUNTS").rows)
conn.query("COMMIT")
```

```text
True
False
[(0,)]
```

A statement that fails leaves the transaction active, unless its
failure rolled it back; the error's `transaction_active` says which
([Errors and Diagnostics](10-errors.md)).

## Autocommit

With `autocommit` set, each statement is its own transaction: the
server commits it as it succeeds and rolls it back as it fails, with no
COMMIT sent.

```python
conn.autocommit = True
conn.query("INSERT INTO ACCOUNTS VALUES (1, 100)")
print(conn.in_transaction)
try:
    conn.query("INSERT INTO ACCOUNTS VALUES (1, 200)")
except Exception as e:
    print(type(e).__name__, e.sqlstate, e.transaction_active)
print(conn.query("SELECT BALANCE FROM ACCOUNTS").rows)
```

```text
False
IntegrityError 23000 False
[(100,)]
```

## Cursors and locators keep their transaction

A cursor read in parts lives within its transaction
([Prepared Statements](04-prepared-statements.md)). Under autocommit,
the server granting `fetch-ends`, as it does by default, the transaction
ends as the cursor does: committed when the fetch reads its last row or
the cursor is closed, rolled back when a fetch fails. Without
`fetch-ends` the transaction is left to the program.

```python
numbers = conn.prepare("VALUES 1, 2, 3")
conn.open_cursor(numbers, rows=2)
print(conn.in_transaction)
print(conn.fetch(numbers, rows=2).rows, conn.in_transaction)
```

```text
True
[(3,)] False
```

A large object longer than the server's SERVER.LOB_INLINE_BYTES comes
by its locator, which lasts only as long as its transaction; so a result
that sent a locator keeps its transaction active, under autocommit too,
until the program ends it. Large objects are the matter of milestone M4.

## Reset and change of user

`reset` returns the session to what it was at login, its user and its
cancel key kept: the transaction rolled back; prepared statements,
cursors and temporary tables gone; each setting back at the database's
value. A rolled-back transaction is told by a notice of SQLSTATE 01T01;
each setting changed back, by a status the connection keeps.

```python
conn.autocommit = False
conn.query("SET TIME ZONE INTERVAL '+02:00' HOUR TO MINUTE")
conn.query("INSERT INTO ACCOUNTS VALUES (2, 50)")
print(conn.setting("SESSION.TIME_ZONE"))
conn.reset()
print([(n.sqlstate, n.diagnostics.severity) for n in conn.take_notices()])
print(conn.setting("SESSION.TIME_ZONE"), conn.in_transaction)
```

```text
+02:00
[('01T01', 'NOTICE')]
+00:00 False
```

`change_user` proves another user, or the same again, over the same
connection, by any mechanism, and renews the session as `reset` does,
under a new cancel key. A refusal fails the connection.

```python
from turborel.client import Scram, connect_local

local = connect_local("/run/turborel.sock", "ANN", Trust())
local.change_user("ANN", Scram("ann's secret"))
print(local.authorization)
local.terminate()
```

```text
ANN
```

## Ending the session

`terminate` ends the session; its transaction, if one is active, is
committed or rolled back as SESSION.COMMIT_AT_END says, ON by default.

## See also

[Running Queries](03-queries.md),
[Prepared Statements](04-prepared-statements.md),
[Statements and Cursors](../client/22-statements.md).
