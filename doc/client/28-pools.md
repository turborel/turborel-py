# Pools

[Contents](README.md)

## NAME

`turborel.client.Pool`: a bounded set of connections a program's
threads share.

## SYNOPSIS

```python
Pool(source, config=None)
PoolConfig(max=10, max_idle=10, idle_timeout=600.0, max_lifetime=3600.0, wait=30.0, check=True, reset=())
pool.get() -> Pooled
pool.counts() -> (made, idle)
pool.close()
copy.copy(pool) -> Pool

pooled.release()
pooled.connection -> Connection
with pool.get() as pooled: ...
```

## DESCRIPTION

**Making.** `source` is settings, any object of a `connect` method, or
a function that makes a connection. A copy of a pool is the same pool.

**Getting.** `get` hands out an idle connection that answers, or makes
one while fewer than `max` are made, or waits for one to come back, at
most `wait` seconds. An idle connection idle past `idle_timeout`, older
than `max_lifetime` or lost is closed as `get` meets it; with `check`,
one that does not answer Ping, or ROLLBACK of a server that grants no
`ping`, is closed too, and the next taken.

**Pooled.** A `Pooled` stands for its connection: each attribute read
or set is its connection's. `release`, or the end of its `with` block,
gives it back; after, it reads nothing.

**Giving back.** A connection comes back reset: with `reset` granted,
autocommit off, the protocol's Reset, then the statements of `reset`;
else autocommit off and one pipeline of ROLLBACK, each statement it
prepared closed and destroyed, at most 256 of them, SET SESSION
AUTHORIZATION and SET SCHEMA to its login's user, SET TIME ZONE LOCAL,
then `reset`. A setting a borrower SET stays where the server takes no
Reset. Each wait of the check and the reset is at most 30 seconds. A
connection lost, failing its reset, past `max_lifetime`, or beyond
`max_idle` is closed instead.

**Threads.** The pool is thread-safe, by the standard library's lock
and condition, and starts no thread: each wait is the waiter's own.
`close`, or the end of a `with` block of the pool, closes its idle
connections; those handed out close as they are released.

## ERRORS

| Condition | Raised |
|---|---|
| None comes back within `wait` | `OperationalError`, -919, 08001 |
| The source cannot make one | its failure |
| A pooled connection used after its release | `OperationalError`, -919, 08006 |

## EXAMPLES

```python
from turborel.client import Pool, PoolConfig, Trust, connect

pool = Pool(
    lambda: connect(("127.0.0.1", 7422), "ANN", Trust()), PoolConfig(max=1, wait=0.5)
)
with pool, pool.get() as only:
    try:
        pool.get()
    except Exception as e:
        print(e.sqlstate, e.message)
```

```text
08001 no connection of the pool's 1 came back within 0.5 seconds
```

## SEE ALSO

[Pipelines and Pools](../user/08-pipelines-and-pools.md), the chapter;
[Settings](26-settings.md); [Appendix C](../appendix/c-settings.md).
