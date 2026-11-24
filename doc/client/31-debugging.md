# Debugging Routines

[Contents](README.md)

## NAME

`turborel.client.Connection`'s routine debugger *(extension)*: one
connection attached to the session of another, pausing its routines,
stepping them and reading their frames.

## SYNOPSIS

```python
conn.debug_id() -> int
conn.debug_attach(connection)
conn.debug_detach()
conn.debug_break(name, line, *, schema="", kind=RoutineKind.PROCEDURE, condition=None) -> Breakpoint
conn.debug_clear(number)
conn.debug_breakpoints() -> tuple[Breakpoint, ...]
conn.debug_wait(timeout=None) -> Event | None
conn.debug_stack() -> Pause | None
conn.debug_resume(action=Action.CONTINUE)
conn.debug_interrupt()

RoutineKind.PROCEDURE | RoutineKind.FUNCTION | RoutineKind.TRIGGER
Action.INTO | Action.OVER | Action.OUT | Action.CONTINUE
EventKind.PAUSED | EventKind.TIMED_OUT | EventKind.CANCELLED | EventKind.ENDED
Breakpoint(number, schema, name, line, condition)
Event(kind, pause) | Pause(breakpoint, frames)
Frame(origin, visible, place, line, column, parameters, variables, cursors)
Origin(kind, specific_schema, specific_name, schema, name)
Named(name, data_type, value) | CursorShown(name, open, query)
```

## DESCRIPTION

A procedure, a function or a trigger written in SQL can be run under a
debugger: another connection to the same server, granted `debugger`,
which connecting asks for. Two connections take part. The target runs
its statements as ever; the debugger, often on another thread, attaches
to the target's session and drives it as it pauses
([Debugging Routines](https://github.com/turborel/turborel/blob/main/doc/user/11-debugging.md)
in Turborel's manual).

**Attaching.** `debug_id` gives a connection's ID, as
INFORMATION_SCHEMA.CONNECTIONS shows it. `debug_attach` makes this
connection the debugger of the session of the connection of that ID:
one of its own user's, or any if its user is the database's owner or
holds the role MONITOR. `debug_detach` ends it: the breakpoints go,
the target, if paused, goes on, and the events not yet read are
dropped.

**Breakpoints.** `debug_break` sets a breakpoint at `line`, from 1, of
the text of the routine or trigger `name`: a routine's specific name, or
its name if it is the one routine of `kind` so named, or a trigger's
name. An empty `schema` is the session's default schema. The target
pauses at each statement that begins on the line, where `condition`, a
`<search condition>` over the frame's parameters and variables, is true,
if given. It gives the `Breakpoint` set, its routine named by its
specific name. `debug_clear` clears one by its number; `debug_breakpoints`
gives each set, in the order they were set. The debugger pauses in, and
sees into, only the routines its user owns or holds DEBUG on.

**Waiting.** What the debugger hears of its target, an `Event`, comes
unasked, only between its own requests, and is kept as it comes, wherever
a reply is read; it never ends a request's replies. `debug_wait` gives
the next not yet read: one kept, else the next the server sends, waited
for at most `timeout` seconds, without limit if None. It gives None if
none came in time, or if a notice or a setting's status came instead,
which is taken. A connection over a stream given to `open` waits only
without limit.

An `Event` of `kind` `PAUSED` holds the `Pause`: the number of the
breakpoint it paused at, or None at the end of a step, and its
`frames`, its call stack, the outermost first and the paused
statement's last. `TIMED_OUT` says the target, paused longer than
DEBUGGER.PAUSE_TIMEOUT_MS, went on by itself; `CANCELLED` that its
statement was cancelled while it was paused; `ENDED` that its session
ended, and the debugger is detached.

**Frames.** A `Frame` is a run of a routine's or a trigger's body. Its
`origin`, None of a statement run directly, gives the routine's `kind`,
its specific name and its name. A frame the debugger may not see into
is not `visible`, and shows its origin alone. Its `place` is in
characters from the beginning of the routine's text, and its `line` and
`column` count from 1. Its `parameters`, a trigger's transition
variables, and its `variables` are each a `Named` of its `name`, its
`data_type` as SQL writes it and its `value`, read as
[Values](23-values.md) says; its `cursors` each a `CursorShown` of its
`name`, whether it is `open`, and its `query`. `debug_stack` gives the
target's pause again, or None if it runs.

**Going on.** `debug_resume` tells the paused target how to go on:
`INTO` to its next statement in whatever frame; `OVER` to the next of
this frame or one it returns to; `OUT` to the next of the frame this one
returns to; `CONTINUE` to a breakpoint. `debug_interrupt` tells the
running target to pause at its next statement.

## ERRORS

| Condition | SQLCODE, SQLSTATE |
|---|---|
| `debugger` not granted, before anything is sent | -919, 08006 |
| An ID of no connection served whose session this one may debug | the server's, 08003 |
| A breakpoint in a routine its user neither owns nor holds DEBUG on | -104, 42000 |
| No such routine or line | -103, 42000 |
| A request the target's state does not allow: a resume of a target not paused, a second attach, any but `debug_id` and `debug_attach` attached to none | -910, TBD01 |
| A `timeout` of `debug_wait` over a stream given to `open`, the connection kept | -919, 08006 |
| A reply where an event was waited for | -919, 08006, the connection lost |

The session goes on after each refusal of the server's.

## EXAMPLES

```python
import threading

from turborel.client import Action, Trust, connect

target = connect(("127.0.0.1", 7422), "ANN", Trust())
target.query("CREATE TABLE STAFF (ID INTEGER PRIMARY KEY, SALARY INTEGER)")
target.query("INSERT INTO STAFF VALUES (1, 50000), (2, 60000)")
target.query(
    """CREATE PROCEDURE RAISE_PAY(IN PCT INTEGER) MODIFIES SQL DATA
BEGIN
  DECLARE N INTEGER DEFAULT 0;
  UPDATE STAFF SET SALARY = SALARY * (100 + PCT) / 100;
  SET N = (SELECT COUNT(*) FROM STAFF);
END"""
)
target.query("COMMIT")

debugger = connect(("127.0.0.1", 7422), "ANN", Trust())
debugger.debug_attach(target.debug_id())
point = debugger.debug_break("RAISE_PAY", 4)
print(point.number, point.line)

calling = threading.Thread(target=target.query, args=("CALL RAISE_PAY(10)",))
calling.start()
for step in (Action.OVER, Action.CONTINUE):
    event = debugger.debug_wait(10)
    frame = event.pause.frames[-1]
    print(event.kind.name, event.pause.breakpoint, frame.origin.name, frame.line)
    print([(n.name, n.value) for n in frame.parameters + frame.variables])
    debugger.debug_resume(step)
calling.join()
debugger.debug_detach()
debugger.terminate()
target.query("ROLLBACK")
target.terminate()
```

```text
1 4
PAUSED 1 RAISE_PAY 4
[('PCT', 10), ('N', 0)]
PAUSED None RAISE_PAY 5
[('PCT', 10), ('N', 0)]
```

## SEE ALSO

[Connections](21-connections.md); [Statements and
Cursors](22-statements.md); [Errors](30-errors.md).
