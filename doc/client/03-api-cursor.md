# Cursor

[Contents](README.md)

## NAME

`turborel.Cursor`: a statement run, its rows fetched in order.

## SYNOPSIS

```python
cursor.execute(operation, parameters=None) -> Cursor
cursor.executemany(operation, seq_of_parameters) -> Cursor
cursor.fetchone() -> tuple | None
cursor.fetchmany(size=cursor.arraysize) -> list[tuple]
cursor.fetchall() -> list[tuple]
for row in cursor: ...
cursor.description, cursor.rowcount, cursor.arraysize
cursor.setinputsizes(sizes) | cursor.setoutputsize(size, column=None)
cursor.close()
cursor.connection, cursor.warning, cursor.last_generated
```

## DESCRIPTION

**execute** runs `operation`, each `?` of it a value of `parameters`, a
sequence, in order. Without parameters the statement is sent as it is;
with them it is prepared once, the connection keeping it by its text,
and executed with the values. A query's rows are read whole.

**executemany** executes `operation` once for each set of values, in one
pipeline: it stops at the first failure, which it raises, the
executions after it undone, those before kept in the transaction.

**description** gives a query's columns, seven items each: the name,
the type code, the data type the server gave it, which the module's
type objects compare with, a display size, None, an internal size, the
length of a string type, the precision and scale of an exact numeric
type, and whether it may be null; None of a statement not a query.
**rowcount** is the rows a query gave, or a statement changed, as the
server told it; -1 if it did not.

**Fetching.** `fetchone` gives the next row, or None at the end;
`fetchmany` the next `size`, `arraysize` by default, 1; `fetchall` the
rest. A cursor iterates its rows. `setinputsizes` and `setoutputsize` do
nothing: the server gives each parameter's type, and every value is read
whole.

**Extensions.** `warning` is the SQLSTATE of the last statement's
warning, of class 01; `last_generated` the identity values an INSERT
generated, as SQL writes them.

## ERRORS

| Condition | Raised |
|---|---|
| A method of a cursor closed, or of a connection closed | `InterfaceError`, -910, TB910 |
| Parameters not a sequence, a mapping or a string | `InterfaceError`, -910, TB910 |
| A fetch after a statement not a query | `InterfaceError`, -910, TB910 |
| The statement's failure | the server's |

## EXAMPLES

```python
import turborel

conn = turborel.connect(host="127.0.0.1", port=7422, user="ANN")
cursor = conn.cursor()
cursor.execute("CREATE TABLE BOOKS (ID INTEGER, TITLE VARCHAR(20))")
cursor.executemany("INSERT INTO BOOKS VALUES (?, ?)", [(1, "Emma"), (2, "Persuasion")])
print(cursor.rowcount)
cursor.execute("SELECT ID, TITLE FROM BOOKS WHERE ID >= ? ORDER BY ID", (1,))
print([d[0] for d in cursor.description], cursor.rowcount)
for row in cursor:
    print(row)
conn.rollback()
conn.close()
```

```text
2
['ID', 'TITLE'] 2
(1, 'Emma')
(2, 'Persuasion')
```

## SEE ALSO

[Connection](02-api-connection.md); [Statements and
Cursors](22-statements.md), the low-level client's.
