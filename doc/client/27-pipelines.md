# Pipelines

[Contents](README.md)

## NAME

`turborel.client.Pipeline`: requests written at once, one outcome each,
in order.

## SYNOPSIS

```python
conn.pipeline() -> Pipeline
pipeline.query(sql) -> Pipeline
pipeline.execute(statement, values=()) -> Pipeline
pipeline.on_error(OnError.CONTINUE | OnError.SKIP) -> Pipeline
len(pipeline) -> int
pipeline.run() -> list[Rowset | Complete | Error | Skipped]

SKIPPED
PIPELINE_WINDOW = 65536
```

## DESCRIPTION

A pipeline queues queries and executions on its connection. `run`
writes them, a window of at most `PIPELINE_WINDOW` bytes at a time, a
request longer than that alone in its own, and reads the window's
replies before writing the next; it gives one outcome for each request,
in the order queued: a query's `Rowset`, another statement's
`Complete`, or the request's failure, the exception, given and not
raised. `run` empties the pipeline.

**Continue on error**, the default: each request runs, a failure its
own outcome alone. Under autocommit each request ends its own
transaction.

**Skip on error**: the driver sets a savepoint,
`TURBOREL_PIPELINE_<n>`, before each request but the first. After the
first failure, the requests already run are rolled back to the
savepoint set after the failed one, the requests not yet written are
never sent, and each after the failure is `SKIPPED`; the first
savepoint is released. The batch is one transaction, its statements
none ending it; under autocommit, of a batch that began no transaction,
it is committed as it ends.

## ERRORS

| Condition | Raised |
|---|---|
| The connection lost | its failure, -919, 08006; what was answered before is not given |
| Of a skipping batch, undoing the requests after the failure fails | that failure |
| A request's own failure | given as its outcome, not raised |

## EXAMPLES

```python
from turborel.client import Trust, connect

conn = connect(("127.0.0.1", 7422), "ANN", Trust())
answers = (
    conn.pipeline()
    .query("VALUES 1")
    .query("SELECT * FROM NOWHERE")
    .query("VALUES 3")
    .run()
)
for answer in answers:
    print(getattr(answer, "rows", answer))
conn.query("ROLLBACK")
```

```text
[(1,)]
table ANN.NOWHERE is not defined
[(3,)]
```

## SEE ALSO

[Pipelines and Pools](../user/08-pipelines-and-pools.md), the chapter;
[Statements and Cursors](22-statements.md).
