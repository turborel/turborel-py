# Copy, Import and Export

[Contents](README.md)

## NAME

`turborel.client`: copying rows in bulk, importing a source's records,
and exporting a query's rows.

## SYNOPSIS

```python
conn.copy_in(table, columns=()) -> Copying
conn.copy_rows(table, columns, rows) -> int
Copying.send(row) | Copying.ping() | Copying.finish() -> int | Copying.abandon()

conn.export(sql, out, form=ExportFormat.CSV) -> int
read_native(data) -> (columns, rows)

import_rows(conn, source, how, rejected=None) -> Imported
Import(table, batch=1000, skip=False)
Imported(rows, rejected)
Rejected(position, cause)
ImportFailure(where, cause, committed, rolled_back)

Delimited(data, dialect=None)
Dialect.csv() | Dialect.tsv()
Dialect.with_delimiter(c) | .with_header() | .with_null(text) | .with_max_record(octets)
Source: headings() -> list[Heading] | None; record() -> Record | None
Heading(name, data_type=None) | Record(values, position) | Position(record, line=None)
SourceError(position, message): .where, .reason
```

## DESCRIPTION

**Copy.** `copy_in` begins a copy into `table`, as SQL names it, of
`columns`, in order, all of the table's if none; it needs `copy`. `send`
sends a row, the rows waiting going in one CopyData once they are
`CHUNK_BYTES`, 256 KiB, with no reply; `finish` sends the rest and ends
the copy, giving the rows inserted; `abandon` gives it up, every row
undone. `ping` pings the server during the copy. A copy is all or
nothing: a row the server refuses fails `finish`, its failure's detail
naming the row, as `row 7 of the copy`. Under autocommit a copy is its
own transaction; within one it runs under a savepoint of its own. Until
it ends, the connection takes no other request. As a context manager a
copy left neither finished nor abandoned is abandoned. `copy_rows`
copies the rows an iterator gives.

**Export.** `export` runs the query `sql` and writes its rows to `out`, a
binary stream, a batch at a time as they come. As CSV, RFC 4180: a
header of the columns' names, then a record for each row, ended by CR
LF, a field quoted where it holds a comma, a quote, a line break or
spaces at either end, its quotes doubled, a null an empty field and an
empty string `""`. Each value is written as Turborel writes it as text:
an exact number with its scale, an approximate one as
`<mantissa>E<exponent>`, a binary string in upper case hexadecimal, a
datetime to its type's precision, an interval by its fields, a truth
value TRUE or FALSE, JSON as its text, XML as its serialization, a UUID
hyphenated, and an array, row, multiset, structured value or reference
as its literal. As `ExportFormat.NATIVE`, the protocol's frames, a
Description, the Rows as the server sent them, and a Complete;
`read_native` reads them back, every value as it was.

**Import.** `import_rows` inserts the records of `source` into the table
`how.table` names, through one prepared INSERT of the columns the
source's headings name, or else of the table's columns in order. It
begins only with no transaction active, and commits `how.batch` rows at
a time, all at once if 0. A string for a character column is assigned
as INSERT assigns, padded or cut of spaces, else refused. Where `copy`
is granted, `how.skip` is false and no column is a large object's, the
rows go by copy, a copy to each batch. A field of more than
`LOB_INLINE_OCTETS` for a large object column is sent ahead by its
locator. A row refused stops the import, the batch under way rolled
back; with `how.skip`, a row refused alone, or of too many or too few
fields, is skipped and given to `rejected` as a `Rejected`. `Imported`
counts the rows committed and those skipped.

**Sources.** A source has two methods: `headings`, asked once before
the first record, its fields' names and types, or None; and `record`,
asked until it gives None, each record's values, strings or None, and
its `Position`, its number from 1 and its line. It raises `SourceError`
of what it cannot read, and where. `Delimited` reads CSV or
tab-separated text, a record at most `max_record` octets, 16 MiB by
default; a field written as the dialect's null text, not in quotes, is
None, an empty one by default; a byte order mark beginning the input is
passed over.

## ERRORS

| Condition | Raised |
|---|---|
| `copy` not granted | `OperationalError`, -919, 08006, before anything is sent |
| A request while a copy is under way | `InterfaceError`, -910, TB910 |
| A row a copy refuses | the server's, at `finish` |
| A statement that is no query, or a write to `out` that fails, of an export | `OperationalError`, -919, 08006; the connection goes on |
| Input to `read_native` that is not native rows | `OperationalError`, -919, 08006 |
| An import that stops | `ImportFailure`: its SQL condition's SQLCODE and SQLSTATE, or of input that cannot be read -301, 22000 |
| A delimiter not one ASCII character, or a quote or line break | `InterfaceError`, -910, TB910 |
| A source's record that cannot be read | `SourceError`, a `DataError`, -301, 22000, its `where` and `reason` |

`ImportFailure` says, as turborel-client does, where the record began,
why, and the rows committed and rolled back: `record 2, line 2: SQLCODE
-301 (SQLSTATE 22001): ...; 0 rows committed, 1 rolled back`.

## EXAMPLES

```python
import io

from turborel.client import Delimited, Dialect, Import, Trust, connect, import_rows

conn = connect(("127.0.0.1", 7422), "ANN", Trust())
conn.query("CREATE TABLE STOCK (ITEM VARCHAR(10), QTY INTEGER)")
conn.query("COMMIT")
text = io.BytesIO(b"ITEM\tQTY\nbolt\t40\nnut\t\\N\n")
dialect = Dialect.tsv().with_header().with_null("\\N")
print(import_rows(conn, Delimited(text, dialect), Import("STOCK")))
out = io.BytesIO()
conn.export("SELECT * FROM STOCK ORDER BY ITEM", out)
print(out.getvalue().decode())
conn.query("COMMIT")
```

```text
Imported(rows=2, rejected=0)
ITEM,QTY
bolt,40
nut,

```

## SEE ALSO

[Copying, Importing and Exporting](../user/07-copying.md), the chapter;
[Large Objects](24-large-objects.md).
