# Connection

[Contents](README.md)

## NAME

`turborel.Connection`: a connection of the standard API.

## SYNOPSIS

```python
conn.cursor() -> Cursor
conn.commit()
conn.rollback()
conn.close()
with conn: ...

conn.autocommit            # read and set
conn.in_transaction, conn.closed
conn.client -> turborel.client.Connection
conn.Error, conn.IntegrityError, ...
```

## DESCRIPTION

A transaction begins with the connection's first statement, as
Turborel's do, and lasts until `commit` or `rollback`; each sends COMMIT
or ROLLBACK only where a transaction is active. `close` ends the
session; a transaction still active is rolled back first, as PEP 249
says, whatever the server's SESSION.COMMIT_AT_END. Closing a connection
closed does nothing. As a context, a connection commits as its block
ends, or of an exception does not, and closes.

**Extensions.** `autocommit`, off by default, makes each statement its
own transaction. `in_transaction` says whether one is active, as the
server last said. `client` is the low-level client's connection beneath,
for all the standard API has no place for: large objects by locator,
copy, export and import, pipelines, notices, settings told, cancel,
Ping, Reset and change of user. Each exception class of the module is
an attribute of the connection too.

**Statements.** The connection keeps the statements its cursors
prepared, 128 of them, by their text, the least used destroyed first; a
statement a reset of the session took is prepared again, once.

## ERRORS

| Condition | Raised |
|---|---|
| A method of a connection closed | `InterfaceError`, -910, TB910 |
| The commit's or rollback's failure | the server's |

## EXAMPLES

```python
import turborel

conn = turborel.connect(host="127.0.0.1", port=7422, user="ANN")
cursor = conn.cursor()
cursor.execute("CREATE TABLE NOTES (N INTEGER)")
conn.commit()
cursor.execute("INSERT INTO NOTES VALUES (1)")
print(conn.in_transaction)
conn.close()
again = turborel.connect(host="127.0.0.1", port=7422, user="ANN")
check = again.cursor()
check.execute("SELECT COUNT(*) FROM NOTES")
print(check.fetchone())
again.close()
```

```text
True
(0,)
```

## SEE ALSO

[Cursor](03-api-cursor.md); [Connections](21-connections.md), the
low-level client's; [Transactions](../user/05-transactions.md).
