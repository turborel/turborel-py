# Copying, Importing and Exporting

[Contents](README.md)

Rows go into a table in bulk by a copy, with no reply for each; a file
of CSV or tab-separated text goes in by an import; a query's rows come
out by an export, as CSV or as the protocol's own frames. This chapter
uses the low-level client, `turborel.client`.

## Copying rows in

`copy_in(table, columns)` begins a copy into the table, as SQL names it,
of the columns named, in that order, or all of them. `send` sends a row,
many rows going in one message; `finish` ends the copy and gives the
rows inserted. `copy_rows` does all three for the rows an iterator
gives.

```python
from turborel.client import Trust, connect

conn = connect(("127.0.0.1", 7422), "ANN", Trust())
conn.query("CREATE TABLE PARTS (ID INTEGER PRIMARY KEY, NAME VARCHAR(10))")
conn.query("COMMIT")
with conn.copy_in("PARTS", ("ID", "NAME")) as copy:
    for part, name in [(1, "bolt"), (2, "nut")]:
        copy.send((part, name))
    print(copy.finish())
print(conn.copy_rows("PARTS", (), iter([(3, "gear"), (4, "cam")])))
conn.query("COMMIT")
```

```text
2
2
```

A copy is all or nothing. A row the server refuses fails the copy at
its end, every row of it undone, and the failure's detail names the
row. Within a transaction the copy runs under a savepoint of its own,
so a copy that fails undoes its own rows alone; under autocommit it is
its own transaction. A copy left neither finished nor abandoned when its
`with` block ends is abandoned. Until a copy ends the connection takes
only its rows and `ping`; another request fails with SQLSTATE TB910.

```python
try:
    conn.copy_rows("PARTS", (), [(5, "pin"), (1, "again")])
except Exception as e:
    print(e.sqlstate, e.diagnostics.detail)
print(conn.query("SELECT COUNT(*) FROM PARTS").rows)
conn.query("COMMIT")
```

```text
23000 row 2 of the copy
[(4,)]
```

## Importing delimited text

`import_rows(conn, source, Import(table))` inserts a source's records
into a table. `Delimited` reads CSV, as RFC 4180 writes it, or
tab-separated text, from a binary stream, a record at a time; its
`Dialect` says the delimiter, whether a header names the columns, and
the text of a null, an empty field by default. Without a header the
fields are the table's columns in order.

```python
import io

from turborel.client import Delimited, Dialect, Import, import_rows

data = io.BytesIO(b"id,name\n10,washer\n11,spring\n")
imported = import_rows(
    conn, Delimited(data, Dialect.csv().with_header()), Import("PARTS")
)
print(imported)
```

```text
Imported(rows=2, rejected=0)
```

An import commits its rows a batch at a time, 1000 by default, or all
at once with `batch=0`; it begins only with no transaction active. A
string for a character column is assigned to it as INSERT assigns, so
one too long is refused, not cut. Where the server grants `copy` and no
column is a large object's, the rows go by copy, a batch to each. A
field longer than 64 KiB for a large object column is sent ahead as a
large object, by its locator.

A row that fails stops the import, the batch under way rolled back,
with an `ImportFailure` that says where the record began, why, and how
many rows were committed and rolled back. With `skip=True` a failing
row is skipped instead, and given to the program.

```python
skipped = []
data = io.BytesIO(b"12,clip\n13,a name too long\n14\n")
print(import_rows(conn, Delimited(data), Import("PARTS", skip=True), skipped.append))
for row in skipped:
    print(row)
```

```text
Imported(rows=1, rejected=2)
record 2, line 2: SQLCODE -301 (SQLSTATE 22001): a value of 15 characters, not spaces beyond 10, does not fit CHARACTER VARYING(10) [ISO/IEC 9075:1992 §13.8 GR4b iii, §9.2 GR3e ii]; skipped
record 3, line 3: 1 fields, for 2 columns; skipped
```

A source is any object with the methods `headings` and `record`, as
[Copy, Import and Export](../client/25-copy.md) describes, so a program
imports from a format of its own.

## Exporting a query's rows

`export(sql, out)` runs a query and writes its rows to a binary stream
as they come: as CSV, a header of the columns' names, then a record for
each row; or, with `ExportFormat.NATIVE`, as the protocol's own frames,
which `read_native` reads back with every value as it was.

```python
from turborel.client import ExportFormat, read_native

out = io.BytesIO()
print(conn.export("SELECT ID, NAME FROM PARTS WHERE ID < 3 ORDER BY ID", out))
print(out.getvalue())
native = io.BytesIO()
conn.export(
    "SELECT ID, NAME FROM PARTS WHERE ID < 3 ORDER BY ID", native, ExportFormat.NATIVE
)
native.seek(0)
print(read_native(native)[1])
conn.query("COMMIT")
```

```text
2
b'ID,NAME\r\n1,bolt\r\n2,nut\r\n'
[(1, 'bolt'), (2, 'nut')]
```

A value is written in CSV as Turborel writes it as text: an
approximate number as `5E-1`, a binary string in hexadecimal, an array
as its literal, and a null as an empty field.

## See also

[Copy, Import and Export](../client/25-copy.md), the reference page;
[Large Objects](06-large-objects.md).
