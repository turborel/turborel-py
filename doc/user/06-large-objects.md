# Large Objects

[Contents](README.md)

A CHARACTER LARGE OBJECT or BINARY LARGE OBJECT value may be far longer
than a program wants to hold at once. The server sends a short one whole
in its row, and a longer one by its locator, which the program reads a
range at a time. A program writes a long value a piece at a time and
passes it as a parameter. This chapter uses the low-level client,
`turborel.client`.

## Whole, or by its locator

A large object of at most the server's SERVER.LOB_INLINE_BYTES, 64 KiB
by default, comes whole: a CLOB as a `str`, a BLOB as `bytes`. A longer
one comes as a `turborel.LobLocator`: whether it is binary, its locator,
and its lengths in octets and, of a CLOB, in characters.

```python
from turborel import LargeObject
from turborel.client import Trust, connect

conn = connect(("127.0.0.1", 7422), "ANN", Trust())
conn.query("CREATE TABLE DOCS (ID INTEGER, BODY CLOB(1M))")
insert = conn.prepare("INSERT INTO DOCS VALUES (?, ?)")
conn.execute(insert, (1, LargeObject("short")))
conn.execute(insert, (2, LargeObject("é" * 40_000)))
conn.query("COMMIT")
for doc, body in conn.query("SELECT ID, BODY FROM DOCS ORDER BY ID").rows:
    print(doc, body if isinstance(body, str) else (body.octets, body.characters))
```

```text
1 short
2 (80000, 40000)
```

A parameter wrapped in `LargeObject` is sent whole, as a large object;
a `str` or `bytes` alone would be sent as a character or binary string.

## Reading by ranges

`read_lob(lob, start, count)` reads at most `count` octets from octet
`start`, from 0; with `characters=True`, a CLOB's characters, whole
ones, as UTF-8. A read gives at most 256 KiB. `lob_reader(lob)` gives
the whole value as a binary stream, read a chunk at a time. Both take a
value held whole too, reading it from the value itself.

```python
[(body,)] = conn.query("SELECT BODY FROM DOCS WHERE ID = 2").rows
print(conn.read_lob(body, 0, 3, characters=True).decode())
print(len(conn.lob_reader(body).read()))
```

```text
ééé
80000
```

## How long a locator lasts

A locator is valid until its transaction ends; under autocommit a result
that sent one keeps its transaction active until the program ends it.
`free_lob` ends a locator sooner. `hold_lob` keeps it valid past its
transaction's commit, until it is freed or a rollback ends it. A locator
no longer valid fails with SQLSTATE 0F001.

```python
conn.hold_lob(body)
conn.query("COMMIT")
print(conn.read_lob(body, 0, 1, characters=True).decode())
conn.free_lob(body)
try:
    conn.read_lob(body, 0, 1)
except Exception as e:
    print(e.sqlstate)
conn.query("ROLLBACK")
```

```text
é
0F001
```

## Writing a piece at a time

`create_lob(binary=...)` makes an empty large object and gives a binary
stream to write it with; `finish` gives its locator, to pass as a
parameter within the same transaction. A CLOB's octets are UTF-8, and a
character may be split between writes.

```python
writer = conn.create_lob(binary=False)
for part in ("chapter one, ", "chapter two"):
    writer.write(part.encode("utf-8"))
book = writer.finish()
conn.execute(insert, (3, book))
print(conn.query("SELECT BODY FROM DOCS WHERE ID = 3").rows)
conn.query("COMMIT")
```

```text
[('chapter one, chapter two',)]
```

## See also

[Large Objects](../client/24-large-objects.md), the reference page;
[Transactions](05-transactions.md).
