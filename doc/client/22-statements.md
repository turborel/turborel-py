# Statements and Cursors

[Contents](README.md)

## NAME

`turborel.client.Connection`: running statements, prepared statements
and their cursors, and what each completion told.

## SYNOPSIS

```python
conn.query(sql) -> Rowset | Complete
conn.query_into(sql, sink) -> int | Complete
conn.query_many(sql) -> Ran
conn.set_query_attributes(attributes)

conn.prepare(sql) -> Statement
conn.execute(statement, values=()) -> Rowset | Complete
conn.open_cursor(statement, values=(), rows=0, cursor=0) -> Batch
conn.fetch(statement, rows=0, cursor=0) -> Batch
conn.close_cursor(statement, cursor=0)
conn.describe(statement) -> Statement
conn.describe_cursor(statement, cursor=0) -> tuple[Column, ...]
conn.deallocate(statement)

conn.autocommit, conn.in_transaction
conn.rows_affected, conn.last_generated, conn.server_time
conn.commit_position, conn.warning, conn.conditions
```

## DESCRIPTION

**Running a statement.** `query` sends one statement and reads its
outcome whole: a `Rowset` of a query's `columns` and `rows`, each row a
tuple, or a `Complete` of another statement, its `sqlcode` and
`sqlstate`. `query_into` gives a query's rows to `sink` instead, a batch
at a time as they come: `sink.columns(columns)` once, then
`sink.rows(rows)` for each batch; it returns the rows given, or another
statement's `Complete`. A statement that changes no row completes with
SQLCODE 100 and SQLSTATE 02000.

**Several statements.** `query_many` sends a text of several
statements as one request, which needs `multi-statement`. The server
runs them in turn and stops at the first failure. The `Ran` it gives
holds `outcomes`, one for each statement run, and `failure`, the
exception of the one that failed, or None. A text of no statement gives
one `Complete`. A failure of the connection is raised, not held.

**Query attributes.** `set_query_attributes` takes pairs of a name and
a value, which every later statement carries until they are set again,
and which SQL reads by QUERY_ATTRIBUTE; it needs `query-attributes`
unless the pairs are none.

**Prepared statements.** `prepare` prepares `sql`, its dynamic
parameters written `?`, under the connection's next statement number.
The `Statement` holds its `number`, its `parameters`, each a `Parameter`
of a `data_type`, in the order of their marks, and a query's `columns`,
none of another statement. `execute` runs it with `values`, one for each
mark, as `query` runs a statement. A statement lasts until it is
deallocated or the session reset, across transactions.

**Cursors.** `open_cursor` executes a query and takes at most `rows` of
its rows, all if 0; `fetch` takes the next `rows`; `close_cursor` closes
the cursor before its end. Each gives a `Batch`, its `rows` and whether
`more` are left; the cursor closes itself when its last row is read. A
cursor's number is 0 unless `cursor` gives another, which needs
`cursors`; with it, several cursors of one statement are open at once.

**Describing.** `describe` gives a statement's parameters and columns
as the server has them now; `describe_cursor` an open cursor's columns.
Both need `describe`.

**Transactions.** A transaction begins with the session's first
statement and lasts until COMMIT or ROLLBACK. `in_transaction` says
whether one is active, as the server said after the last request. With
`autocommit` true each statement is its own transaction, ended with it:
committed as it succeeds, rolled back as it fails. A cursor opened under
autocommit, the server granting `fetch-ends`, ends its transaction as it
ends: committed by the fetch that reads its last row or by its close,
rolled back by a fetch that fails. A result that sent a large object's
locator keeps its transaction active.

**What a completion told.** After each statement:

| Member | What | Capability |
|---|---|---|
| `rows_affected` | the rows it changed, or a query returned; None if not told | `row-counts` |
| `last_generated` | the identity values an INSERT generated, as SQL writes them, in its rows' order | `generated-values` |
| `server_time` | a `Timing`: `total`, `queued` and `locks`, in microseconds; None if not told | `row-counts` |
| `commit_position` | the log position of the last commit, kept until another; None if never told | `commit-position` |
| `warning` | the SQLSTATE of its warning, of class 01, or None | |
| `conditions` | each condition it raised, a `Failure` | `conditions` |

Without `conditions` a statement's conditions come as notices, with
`notices` ([Connections](21-connections.md)).

## ERRORS

| Condition | SQLCODE, SQLSTATE |
|---|---|
| The statement's failure, as the server gave it | the server's |
| `query_many`, a numbered cursor, `describe`, `describe_cursor` or query attributes without their capability, before anything is sent | -919, 08006 |
| A cursor not open fetched, closed or described; one open opened again, or its statement deallocated or prepared again | the server's, 24000 |
| A statement deallocated, or of no such number | the server's, 26000 |
| A value of a type the protocol cannot carry | -921, 07006 |
| A value its field cannot hold | -301, 22003 or 22008 |
| A reply out of turn | -919, 08006, the connection lost |

## EXAMPLES

```python
from turborel.client import Trust, connect

conn = connect(("127.0.0.1", 7422), "ANN", Trust())
statement = conn.prepare("VALUES 1, 2, 3")
conn.open_cursor(statement, rows=1, cursor=1)
conn.open_cursor(statement, rows=2, cursor=2)
print(conn.describe_cursor(statement, cursor=1))
print(conn.fetch(statement, cursor=1))
conn.close_cursor(statement, cursor=2)
conn.deallocate(statement)
```

```text
(Column(name=None, data_type=ExactType(precision=1, scale=0), not_null=False),)
Batch(rows=[(2,), (3,)], more=False)
```

```python
ran = conn.query_many("VALUES 1; VALUES 2")
print([outcome.rows for outcome in ran.outcomes], ran.failure)
print(conn.server_time)
```

```text
[[(1,)], [(2,)]] None
Timing(total=4, queued=0, locks=0)
```

## SEE ALSO

[Running Queries](../user/03-queries.md),
[Prepared Statements](../user/04-prepared-statements.md),
[Transactions](../user/05-transactions.md),
[Errors](30-errors.md).
