# Large Objects

[Contents](README.md)

## NAME

`turborel.client.Connection`: large objects read by their locators, and
written a piece at a time.

## SYNOPSIS

```python
conn.read_lob(lob, start, count, *, characters=False) -> bytes
conn.lob_reader(lob) -> LobReader
conn.create_lob(*, binary) -> LobWriter
conn.free_lob(lob) -> Complete
conn.hold_lob(lob) -> Complete

LobWriter.write(data) -> int
LobWriter.flush()
LobWriter.finish() -> LobLocator

Lob = LobLocator | str | bytes
CHUNK_OCTETS = 262144
LOB_INLINE_OCTETS = 65536
```

## DESCRIPTION

**Values.** A CLOB or BLOB of at most the server's
SERVER.LOB_INLINE_BYTES comes whole in its row, a `str` or `bytes`; a
longer one as a `LobLocator`: `binary`, `locator`, `octets` and, of a
CLOB, `characters`. A parameter is a large object sent whole when
wrapped in `turborel.LargeObject`, or a `LobLocator` the client made or
was given.

**Reading.** `read_lob` reads at most `count` octets of `lob` from
octet `start`, from 0, or with `characters` a CLOB's whole characters,
as UTF-8; at most `CHUNK_OCTETS`, 256 KiB, a read, fewer only at its
end or a chunk's. `lob_reader` gives `lob`'s octets as a binary stream
(`io.RawIOBase`), a chunk read at a time. A value held whole is read
from itself, with no request.

**Lasting.** A locator is valid until its transaction ends, and a
result that sent one keeps its transaction active, under autocommit
too. `free_lob` ends it, and the value it named. `hold_lob` keeps it
valid past its transaction's commit, until it is freed or a rollback
ends it.

**Writing.** `create_lob` makes an empty BLOB if `binary`, else an empty
CLOB, and gives a `LobWriter`, a binary stream. `write` adds octets, a
CLOB's UTF-8, a character free to split between writes, sent in Appends
of `CHUNK_OCTETS`; `flush` sends what is waiting; `finish` sends the
rest and gives the `LobLocator`, its lengths counted, to pass as a
parameter within its transaction. `LOB_INLINE_OCTETS` is the longest
field an import sends whole for a large object column.

## ERRORS

| Condition | SQLCODE, SQLSTATE |
|---|---|
| A locator no longer valid | the server's, 0F001 |
| `free_lob` or `hold_lob` of a value held whole | -301, 22000 |
| A CLOB written that is not UTF-8, or longer than its column | the server's, 22021 or 22001 |
| A reply out of turn | -919, 08006, the connection lost |
| A server that sent less of a value than its length, to a `LobReader` | -919, 08006; the connection goes on |

## EXAMPLES

```python
from turborel import LargeObject
from turborel.client import Trust, connect

conn = connect(("127.0.0.1", 7422), "ANN", Trust())
conn.query("CREATE TABLE BLOBS (DATA BLOB(1M))")
conn.execute(
    conn.prepare("INSERT INTO BLOBS VALUES (?)"),
    (LargeObject(bytes(range(256)) * 300),),
)
conn.query("COMMIT")
[(data,)] = conn.query("SELECT DATA FROM BLOBS").rows
print(data)
print(conn.read_lob(data, 254, 4))
conn.query("ROLLBACK")
```

```text
LobLocator(binary=True, locator=1, octets=76800, characters=76800)
b'\xfe\xff\x00\x01'
```

## SEE ALSO

[Large Objects](../user/06-large-objects.md), the chapter;
[Statements and Cursors](22-statements.md).
