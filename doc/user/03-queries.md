# Running Queries

[Contents](README.md)

A connection runs one statement at a time: a query, which gives columns
and rows, or any other statement, which gives its completion. This
chapter runs statements with the low-level client, `turborel.client`;
the standard API runs them by its cursors
([Cursor](../client/03-api-cursor.md)).

## A statement and its outcome

`query` runs one statement of SQL text. A query's outcome is a `Rowset`,
its columns and all its rows; another statement's is a `Complete`, its
SQLCODE and SQLSTATE.

```python
from turborel.client import Trust, connect

conn = connect(("127.0.0.1", 7422), "ANN", Trust())
conn.query(
    "CREATE TABLE STAFF (ID INTEGER GENERATED ALWAYS AS IDENTITY,"
    " NAME VARCHAR(20), SALARY DECIMAL(9,2))"
)
done = conn.query(
    "INSERT INTO STAFF (NAME, SALARY) VALUES ('Ada', 5200.00), ('Grace', 6100.50)"
)
print(done.sqlcode, done.sqlstate)
staff = conn.query("SELECT NAME, SALARY FROM STAFF ORDER BY NAME")
print([column.name for column in staff.columns])
print(staff.rows)
```

```text
0 00000
['NAME', 'SALARY']
[('Ada', Decimal('5200.00')), ('Grace', Decimal('6100.50'))]
```

A row is a tuple of its columns' values, null as `None`. A statement
that finds no row to change completes with SQLCODE 100 and SQLSTATE
02000; a query that returns none gives a `Rowset` of no rows.

```python
none = conn.query("UPDATE STAFF SET SALARY = 0 WHERE NAME = 'Nobody'")
print(none.sqlcode, none.sqlstate)
print(conn.query("SELECT NAME FROM STAFF WHERE SALARY > 9000").rows)
```

```text
100 02000
[]
```

Each column's `data_type` is the type the server gave it, and each value
is of the Python type [Appendix A](../appendix/a-types.md) gives for it:
an exact number a `decimal.Decimal`, or an `int` of scale 0; a character
string a `str`; a datetime a `datetime.date`, `time` or `datetime`; an
interval a `turborel.Interval`; and so on.

## Rows as they come

`query_into` gives a query's rows to a sink of the program's, a batch at
a time as they come, so a large result is never held whole. The sink has
two methods: `columns`, called once before the rows, and `rows`, called
with each batch. `query_into` returns the number of rows given, or, for
a statement not a query, its completion.

```python
class Printed:
    def columns(self, columns):
        print("columns:", [column.name for column in columns])

    def rows(self, rows):
        print("batch of", len(rows))


print(conn.query_into("SELECT NAME FROM STAFF", Printed()))
```

```text
columns: ['NAME']
batch of 2
2
```

## What a completion tells

After each statement the connection keeps what its completion told.

| Member | What |
|---|---|
| `rows_affected` | the rows the statement changed, or a query returned |
| `last_generated` | the identity values an INSERT generated, as SQL writes them, in its rows' order |
| `server_time` | the server's time for the statement in microseconds: `total`, `queued`, and waiting for `locks` |
| `commit_position` | the log position of the last commit |
| `warning` | the SQLSTATE of the statement's warning, of class 01, or None |
| `conditions` | each condition the statement raised |

```python
conn.query(
    "INSERT INTO STAFF (NAME, SALARY) VALUES ('Edsger', 4800), ('Barbara', 5900)"
)
print(conn.rows_affected, conn.last_generated)
conn.query("COMMIT")
print(conn.commit_position)
conn.query("SELECT CAST(NAME AS CHAR(3)) FROM STAFF")
print(conn.warning, [c.message for c in conn.conditions])
```

```text
2 ('3', '4')
2083
01004 ['the statement completed with warning: string data, right truncation']
```

Each is told only where the server granted its capability, as it does by
default: `row-counts`, `generated-values`, `commit-position` and
`conditions`. Without `conditions`, a statement's conditions come as
notices, with `notices` ([Errors and Diagnostics](10-errors.md)).

## Several statements at once

`query_many` sends a text of several statements, separated by
semicolons, as one request. The server runs them in turn and stops at
the first that fails; the outcome, a `Ran`, holds each statement's
outcome and the failure that stopped the rest.

```python
ran = conn.query_many("VALUES 1; SELECT * FROM NOWHERE; VALUES 3")
print(len(ran.outcomes), ran.failure.sqlstate, ran.failure.message)
```

```text
1 2A000 table ANN.NOWHERE is not defined
```

A text of no statement gives one completion.

## Query attributes

`set_query_attributes` gives name and value pairs that every later
statement carries, until they are set again; SQL reads them by
QUERY_ATTRIBUTE. An application may label its statements so.

```python
conn.set_query_attributes([("request", "r-118")])
print(conn.query("VALUES QUERY_ATTRIBUTE('request')").rows)
conn.set_query_attributes([])
```

```text
[('r-118',)]
```

## XML and UUID values

An XML value is a `turborel.Xml`, holding its text; `nodes()` parses
that text into its text and its elements, as `xml.etree.ElementTree`
elements. A document type declaration is refused, so a value cannot
declare an entity, and text not well-formed fails with SQLSTATE 2200M.
A UUID is a `uuid.UUID`, made of its 16 octets or of its text.

```python
import uuid

from turborel import Xml

conn.query("CREATE TABLE ORDERS (ID UUID, BODY XML)")
insert = conn.prepare("INSERT INTO ORDERS VALUES (?, ?)")
conn.execute(
    insert,
    (
        uuid.UUID("919108f7-52d1-4320-9bac-f847db4148a8"),
        Xml('<order no="18"><item>jam</item></order>'),
    ),
)
[(order_id, body)] = conn.query("SELECT ID, BODY FROM ORDERS").rows
print(order_id, body.text)
[order] = body.nodes()
print(order.tag, order.get("no"), order.findtext("item"))
```

```text
919108f7-52d1-4320-9bac-f847db4148a8 <order no="18"><item>jam</item></order>
order 18 jam
```

A value the server cannot serialize, such as an attribute standing
alone, fails the fetch with SQLSTATE 2200W.

## See also

[Prepared Statements](04-prepared-statements.md),
[Transactions](05-transactions.md),
[Statements and Cursors](../client/22-statements.md).
