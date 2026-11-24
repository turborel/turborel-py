# Debugging Routines

[Contents](README.md)

*(extension)* A procedure, a function or a trigger written in SQL can be
run under a debugger. The debugger is another connection to the same
server. It attaches to the session that runs the routine, sets
breakpoints at lines of the routine's text, and, each time that session
pauses, reads its call stack, each frame's parameters, variables and
cursors, and tells it how to go on. The low-level client's connection
does each of these, granted `debugger`, which connecting asks for.

## Who may debug what

A connection attaches to the session of another connection of its own
user. The database's owner, and a user granted the role MONITOR, attach
to any connection's session, as they see every connection in
INFORMATION_SCHEMA.CONNECTIONS.

Attaching shows nothing by itself. The debugger sets breakpoints in,
pauses in and sees the variables of only the routines its user owns or
holds DEBUG on, which GRANT DEBUG gives as GRANT EXECUTE gives its
privilege. A frame of any other routine is shown by its name alone.

## Two sessions

The session to debug tells its connection's ID with `debug_id`. Here
ANN's first connection, the target, defines a procedure and learns its
ID.

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
print("This is connection", target.debug_id())
```

```text
This is connection 2
```

ANN's second connection, the debugger, attaches to it and sets a
breakpoint at line 4 of the procedure's text, its UPDATE. The
breakpoint names the procedure by its specific name, as a routine's name
may be overloaded.

```python
debugger = connect(("127.0.0.1", 7422), "ANN", Trust())
debugger.debug_attach(target.debug_id())
point = debugger.debug_break("RAISE_PAY", 4)
print(point)
```

```text
Breakpoint(number=1, schema='ANN', name='RAISE_PAY_1', line=4, condition=None)
```

The target calls the procedure on a thread of its own. Its session
pauses as it comes to line 4, and its CALL completes only once the
debugger lets it go on. The debugger waits for the pause, at most 10
seconds here, and is shown the call stack, the outermost frame first.

```python
def show(event):
    print(event.kind.name, "at breakpoint", event.pause.breakpoint)
    for frame in event.pause.frames:
        origin = frame.origin
        print(f"  {origin.kind.name} {origin.schema} {origin.name}", end=" ")
        print(f"line {frame.line} column {frame.column}")
        for named in frame.parameters + frame.variables:
            print("   ", named.name, named.data_type, "=", named.value)


called = []
calling = threading.Thread(
    target=lambda: called.append(target.query("CALL RAISE_PAY(10)"))
)
calling.start()
show(debugger.debug_wait(10))
```

```text
PAUSED at breakpoint 1
  PROCEDURE ANN RAISE_PAY line 4 column 3
    PCT INTEGER = 10
    N INTEGER = 0
```

A step over runs the UPDATE and pauses at the next statement, at the end
of a step rather than at a breakpoint.

```python
debugger.debug_resume(Action.OVER)
show(debugger.debug_wait(10))
```

```text
PAUSED at breakpoint None
  PROCEDURE ANN RAISE_PAY line 5 column 3
    PCT INTEGER = 10
    N INTEGER = 0
```

Continuing lets the session run to its next breakpoint, or here to the
end of its CALL, which completes on the target's thread.

```python
debugger.debug_resume(Action.CONTINUE)
calling.join()
print("CALL completed with", called[0].sqlstate)
target.query("ROLLBACK")
```

```text
CALL completed with 00000
```

## Stepping

`Action.INTO` pauses at the next statement, within a routine the
statement invokes too. `Action.OVER` pauses at the next statement of the
same frame, or of the one it returns to. `Action.OUT` pauses at the next
statement of the frame this one returns to. `Action.CONTINUE` runs to a
breakpoint, and `debug_interrupt` pauses a running session at its next
statement.

A breakpoint may carry a condition over the frame's parameters and
variables, and pauses only where it is true.

```python
print(debugger.debug_break("RAISE_PAY", 5, condition="PCT > 5"))
print([p.number for p in debugger.debug_breakpoints()])
```

```text
Breakpoint(number=2, schema='ANN', name='RAISE_PAY_1', line=5, condition='PCT > 5')
[1, 2]
```

`debug_breakpoints` lists the breakpoints, `debug_clear` clears one by
its number, and `debug_stack` gives the paused session's frames again,
or None while it runs.

```python
for number in (1, 2):
    debugger.debug_clear(number)
print(debugger.debug_breakpoints(), debugger.debug_stack())
debugger.debug_detach()
debugger.terminate()
target.terminate()
```

```text
() None
```

Detaching ends the debugging: the breakpoints go, and the target, if
paused, goes on.

## When a pause ends by itself

A paused session holds what it holds, its locks among them. It waits
for its debugger at most DEBUGGER.PAUSE_TIMEOUT_MS, five minutes unless
set, and then goes on by itself, its debugger told so by an event of
kind `TIMED_OUT`. A cancel of its statement ends a pause too,
`CANCELLED`. A debugger that detaches, or whose connection ends, lets
its session go on as if never debugged. A session that ends detaches its
debugger, which is told so, `ENDED`.

`debug_wait` gives None when nothing came within its timeout, so a
program can wait in a loop and do other work between.

## See also

[Debugging Routines](../client/31-debugging.md), the reference page;
[Debugging Routines](https://github.com/turborel/turborel/blob/main/doc/user/11-debugging.md)
in Turborel's manual.
