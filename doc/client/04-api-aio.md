# turborel.aio

[Contents](README.md)

## NAME

`turborel.aio`: the standard API for asyncio, its waits coroutines.

## SYNOPSIS

```python
await turborel.aio.connect(dsn=None, **settings) -> Connection
async with await turborel.aio.connect(...) as conn: ...
conn.cursor() -> Cursor
await conn.commit() | await conn.rollback() | await conn.close()
await cursor.execute(operation, parameters=None)
await cursor.executemany(operation, seq_of_parameters)
await cursor.fetchone() | await cursor.fetchmany(size) | await cursor.fetchall()
async for row in cursor: ...
```

## DESCRIPTION

The same objects as the blocking interface's, with the same names,
type objects, constructors and exceptions; each method that waits on
the server is a coroutine. A connection behaves as the blocking
[Connection](02-api-connection.md) does and a cursor as the
[Cursor](03-api-cursor.md) does, but that a context of either is
`async with`, and a cursor iterates by `async for`.

Beneath is an asyncio client that runs the low-level client's own
requests, each step awaited, over asyncio's streams: TCP, a Unix socket,
or TLS begun on the same port. On Windows a named pipe's reads and
writes run in asyncio's threads. It connects by settings as the
blocking client does: each host in order or at random, TLS by mode,
SCRAM bound by the server's certificate, a server of the role asked.
A connection's `client` gives it, for `ping`, `reset`, `setting` and
the like. Pipelines, pools, copy and large objects are the blocking
low-level client's.

## ERRORS

As the blocking interface gives them.

## EXAMPLES

```python
import asyncio

from turborel import aio


async def main():
    async with await aio.connect(host="127.0.0.1", port=7422, user="ANN") as conn:
        cursor = conn.cursor()
        await cursor.execute("VALUES 1, 2, 3")
        print([row async for row in cursor])


asyncio.run(main())
```

```text
[(1,), (2,), (3,)]
```

## SEE ALSO

[The turborel Module](01-api-module.md), [Connection](02-api-connection.md),
[Cursor](03-api-cursor.md).
