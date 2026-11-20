# Pipelines and Pools

[Contents](README.md)

A pipeline sends a batch of requests in one round trip; a pool shares a
bounded set of connections among a program's threads; the SQL-agent
holds several named connections, one current. This chapter uses the
low-level client, `turborel.client`.

## Pipelines

`conn.pipeline()` gives an empty pipeline. `query` and `execute` queue
requests; `run` writes them at once and reads one outcome for each, in
order: a query's `Rowset`, another statement's `Complete`, or the
request's failure, the driver's exception, not raised.

```python
from turborel.client import Trust, connect

conn = connect(("127.0.0.1", 7422), "ANN", Trust())
conn.query("CREATE TABLE TALLY (N INTEGER PRIMARY KEY)")
conn.query("COMMIT")
insert = conn.prepare("INSERT INTO TALLY VALUES (?)")
conn.autocommit = True
outcomes = (
    conn.pipeline()
    .execute(insert, (1,))
    .execute(insert, (1,))
    .execute(insert, (2,))
    .query("SELECT COUNT(*) FROM TALLY")
    .run()
)
for outcome in outcomes:
    print(type(outcome).__name__, getattr(outcome, "sqlstate", ""))
print(outcomes[-1].rows)
```

```text
Complete 00000
IntegrityError 23000
Complete 00000
Rowset 
[(2,)]
```

Each request is independent: a failure is its request's outcome alone,
and the requests after it run. Under autocommit each request is its own
transaction. The requests are written a window of 64 KiB at a time, its
replies read before the next, so neither side waits on the other.

With `on_error(OnError.SKIP)` the batch stops at its first failure.
The driver sets a savepoint before each request but the first; the
requests after a failed one are rolled back to it and given as
`SKIPPED`, or never sent if their window was not yet written. A
skipping batch is one transaction, committed as it ends under
autocommit, of a batch that began none.

```python
from turborel.client import OnError

batch = conn.pipeline().on_error(OnError.SKIP)
print(batch.execute(insert, (5,)).execute(insert, (5,)).execute(insert, (6,)).run()[1:])
print(conn.query("SELECT N FROM TALLY ORDER BY N").rows)
```

```text
[IntegrityError('PRIMARY KEY ANN.TALLY_PRIMARY1 (N) of ANN.TALLY would be violated: a row of these values is there'), SKIPPED]
[(1,), (2,), (5,)]
```

`run` raises only a failure of the connection, once it is lost, or of
undoing a skipping batch.

## Pools

A `Pool` is a bounded set of connections a program's threads share,
made by settings or by any function that makes a connection. `get`
hands out an idle connection that answers, or makes one while fewer
than `max` are made, or waits for one to come back, at most `wait`
seconds. A pooled connection stands for its connection; it is given
back as it is released, or as its `with` block ends, reset to the
state it logged in with.

```python
from turborel.client import Pool, PoolConfig

pool = Pool(lambda: connect(("127.0.0.1", 7422), "ANN", Trust()), PoolConfig(max=4))
with pool:
    with pool.get() as borrowed:
        borrowed.query("SET TIME ZONE INTERVAL '+03:00' HOUR TO MINUTE")
    with pool.get() as next_one:
        print(next_one.setting("SESSION.TIME_ZONE"), pool.counts())
```

```text
+00:00 (1, 0)
```

A connection comes back reset by the protocol's Reset, autocommit off,
then the statements of `reset`; a server that takes no Reset is reset
by statements in one pipeline. An idle connection is checked by Ping, or
ROLLBACK, before it is handed out. One lost, failing its reset, past
`max_lifetime`, beyond `max_idle`, idle past `idle_timeout`, or failing
its check is closed. `get` fails with SQLSTATE 08001 if none comes back
in time. The pool starts no thread: each wait is the waiting thread's.
`close`, or the end of a `with` block of the pool, closes its idle
connections. [Appendix C](../appendix/c-settings.md) lists the pool's
settings.

## The SQL-agent

An `Agent` holds a program's connections, each named, one current. It
runs CONNECT, SET CONNECTION and DISCONNECT itself, making a connection
through a connector the program gives, a function of the server named
and the user; every other statement goes to the current connection.

```python
from turborel.client import Agent


def connector(server, user):
    return connect((server or "127.0.0.1", 7422), user or "ANN", Trust())


agent = Agent(connector)
agent.query("CONNECT TO '127.0.0.1' AS 'ledger' USER 'ann'")
print(agent.current_name, agent.query("VALUES CURRENT_USER").rows)
agent.query("COMMIT")
agent.query("DISCONNECT ALL")
print(agent.current_connection)
```

```text
LEDGER [('ANN',)]
None
```

## See also

[Pipelines](../client/27-pipelines.md), [Pools](../client/28-pools.md)
and [The SQL-agent](../client/29-sql-agent.md), the reference pages.
