# Prepared Statements

[Contents](README.md)

A statement prepared once is executed as many times as a program wants,
with values for its dynamic parameters, written `?`. The server parses
and plans it once, and a value travels as a value, never as SQL text, so
no value can change what the statement does. This chapter uses the
low-level client, `turborel.client`, as [Running Queries](03-queries.md)
does.

## Prepare and execute

`prepare` gives a `Statement`: the type the server chose for each `?`,
in the order the marks stand, and a query's columns. `execute` runs it
with a value for each mark, giving what `query` gives: a query's
`Rowset`, or another statement's `Complete`.

```python
from decimal import Decimal

from turborel.client import Trust, connect

conn = connect(("127.0.0.1", 7422), "ANN", Trust())
conn.query(
    "CREATE TABLE PARTS (ID INTEGER PRIMARY KEY, NAME VARCHAR(20), PRICE DECIMAL(7,2))"
)
insert = conn.prepare("INSERT INTO PARTS VALUES (?, ?, ?)")
print([p.data_type for p in insert.parameters])
for part, name, price in [
    (1, "bolt", "0.25"),
    (2, "nut", "0.10"),
    (3, "gear", "12.00"),
]:
    conn.execute(insert, (part, name, Decimal(price)))
conn.query("COMMIT")
cheap = conn.prepare("SELECT NAME FROM PARTS WHERE PRICE < ? ORDER BY ID")
print([c.name for c in cheap.columns])
print(conn.execute(cheap, (Decimal("1.00"),)).rows)
```

```text
[ExactType(precision=10, scale=0), CharacterType(varying=True, length=20, octets=False), ExactType(precision=7, scale=2)]
['NAME']
[('bolt',), ('nut',)]
```

A statement stays prepared across transactions, until it is deallocated
or the session is reset. The values a parameter takes are those
[Appendix A](../appendix/a-types.md) gives; a value of a type the
protocol cannot carry fails before it is sent, with SQLSTATE 22000.

## Cursors

`execute` reads a query's rows whole. `open_cursor` opens the query's
cursor and takes at most the rows asked for, all of them if 0; `fetch`
takes the next batch; `close_cursor` closes the cursor before its end.
Each batch, a `Batch`, holds its rows and whether more are left.

```python
first = conn.open_cursor(cheap, (Decimal("100"),), rows=2)
print(first.rows, first.more)
rest = conn.fetch(cheap, rows=2)
print(rest.rows, rest.more)
```

```text
[('bolt',), ('nut',)] True
[('gear',)] False
```

The cursor closes itself when its last row is read. A cursor read in
parts lives in its transaction ([Transactions](05-transactions.md)).
Fetching from a cursor not open, or opening one that is, fails with
SQLSTATE 24000.

## Several cursors of one statement

Each cursor has a number, 0 unless the program gives another. With the
capability `cursors`, granted by default, several cursors of one
statement are open at once, each with values of its own.

```python
low = conn.open_cursor(cheap, (Decimal("1"),), rows=1, cursor=1)
high = conn.open_cursor(cheap, (Decimal("100"),), rows=1, cursor=2)
print(low.rows, high.rows)
print(conn.fetch(cheap, cursor=2).rows)
conn.close_cursor(cheap, cursor=1)
```

```text
[('bolt',)] [('bolt',)]
[('nut',), ('gear',)]
```

## Describing again

With the capability `describe`, granted by default, `describe` asks the
server for a statement's parameters and columns as they are now, and
`describe_cursor` for an open cursor's columns.

```python
again = conn.describe(cheap)
print(again.columns == cheap.columns)
```

```text
True
```

## Deallocating

`deallocate` destroys a statement. A statement deallocated, or one of
another session, fails with SQLSTATE 26000; one whose cursor is open
fails with 24000.

```python
conn.deallocate(cheap)
try:
    conn.execute(cheap, (Decimal("1"),))
except Exception as e:
    print(type(e).__name__, e.sqlstate)
```

```text
ProgrammingError 26000
```

## See also

[Running Queries](03-queries.md), [Transactions](05-transactions.md),
[Statements and Cursors](../client/22-statements.md).
