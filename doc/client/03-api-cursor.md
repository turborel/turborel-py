# Cursor

[Contents](README.md)

## NAME

`turborel.Cursor`: a statement run, its rows fetched in order.

## SYNOPSIS

```python
cursor.execute(operation, parameters=None) -> Cursor
cursor.executemany(operation, seq_of_parameters) -> Cursor
cursor.callproc(procname, parameters=None) -> tuple
cursor.fetchone() -> tuple | None
cursor.fetchmany(size=cursor.arraysize) -> list[tuple]
cursor.fetchall() -> list[tuple]
for row in cursor: ...
cursor.description, cursor.rowcount, cursor.arraysize
cursor.setinputsizes(sizes) | cursor.setoutputsize(size, column=None)
cursor.close()
cursor.connection, cursor.warning, cursor.last_generated, cursor.parameters
ParameterDescription(mode, position, type_code)
ParameterMode.IN | ParameterMode.INOUT | ParameterMode.OUT
```

## DESCRIPTION

**execute** runs `operation`, each `?` of it a value of `parameters`, a
sequence, in order. Without parameters the statement is sent as it is;
with them it is prepared once, the connection keeping it by its text,
and executed with the values. A query's rows are read whole.

**executemany** executes `operation` once for each set of values, in one
pipeline: it stops at the first failure, which it raises, the
executions after it undone, those before kept in the transaction.

**callproc** calls the procedure `procname`, a schema-qualified name or
a name alone, with a value for each of its arguments, in order: a CALL
of a `?` for each, prepared and kept as `execute` keeps a statement.
The value of an OUT parameter is given, None say, and not sent. It
returns the values given, each of an OUT or INOUT parameter replaced by
what the procedure returned, a row the cursor then fetches too. The
modes come from the server, which tells them of a CALL of an SQL-invoked
procedure with `parameter-modes`; a procedure it tells none of, as one
written in Rust, takes every value as IN.

**description** gives a query's columns, seven items each: the name,
the type code, a `TypeCode` of the data type the server gave it and the
type it was declared with, which the module's type objects compare with
([The turborel Module](01-api-module.md)), a display size, None, an internal size, the
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
generated, as SQL writes them; `parameters`, after `callproc`, each `?`
of the CALL in the order written, a `ParameterDescription` of its
`mode`, a `ParameterMode`, its `position`, the ordinal position of the
procedure's parameter whose argument holds it, and its `type_code`;
None after any other statement.

## ERRORS

| Condition | Raised |
|---|---|
| A method of a cursor closed, or of a connection closed | `InterfaceError`, -910, TB910 |
| Parameters not a sequence, a mapping or a string | `InterfaceError`, -910, TB910 |
| `callproc` of a name not a procedure's, or of a count of values not its arguments' | `InterfaceError`, -910, TB910 |
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

```python
conn = turborel.connect(host="127.0.0.1", port=7422, user="ANN")
cursor = conn.cursor()
cursor.execute(
    "CREATE PROCEDURE TWICE (INOUT N INTEGER, OUT WORD VARCHAR(5))"
    " CONTAINS SQL BEGIN SET N = N * 2; SET WORD = 'done'; END"
)
print(cursor.callproc("TWICE", (21, None)))
print([(p.mode.name, p.position, str(p.type_code)) for p in cursor.parameters])
conn.rollback()
conn.close()
```

```text
(42, 'done')
[('INOUT', 1, 'NUMERIC(10,0)'), ('OUT', 2, 'CHARACTER VARYING(5)')]
```

## SEE ALSO

[Connection](02-api-connection.md); [Statements and
Cursors](22-statements.md), the low-level client's.
