# The SQL-agent

[Contents](README.md)

## NAME

`turborel.client.Agent`: a program's connections, each named, one
current, and the statements that make, choose and end them.

## SYNOPSIS

```python
Agent(connector, connection=None)
connector(server, user) -> Connection
agent.query(sql) -> Rowset | Complete
agent.query_into(sql, sink) -> int | Complete
agent.connection_statement(sql) -> Complete | None
agent.current() -> Connection
agent.current_connection, agent.current_name, agent.warning, agent.is_lost
agent.canceller() -> Canceller | None
agent.terminate()
```

## DESCRIPTION

An agent holds connections, each named, the default one of no name, and
one current. Given `connection`, it begins with it as the default
connection, current. It runs three statements itself, read as
Turborel's parser reads them, each name a character string literal:

- `CONNECT TO '<server>' [AS '<name>'] [USER '<user>']`, or `CONNECT TO
  DEFAULT`: a connection made by `connector`, of the server named, None
  for the default, and of the user, None for the connector's own; named
  as the `AS` name says, else the server's, each read as an identifier,
  a regular one in upper case; current after.
- `SET CONNECTION '<name>'`, or `DEFAULT`: that connection current.
- `DISCONNECT '<name>'`, `DEFAULT`, `CURRENT` or `ALL`: each ended; none
  current after, if the current one was.

Every other statement goes to the current connection, by `query` or
`query_into`. `connection_statement` runs a connection statement and
gives its completion, or None of another statement.

## ERRORS

| Condition | SQLCODE, SQLSTATE |
|---|---|
| A connection statement that breaks its syntax | -102, 2A000 |
| A name not a character string literal | -103, 2A000 |
| CONNECT or SET CONNECTION in an active transaction | -900, 0A001 |
| A user that is no authorization identifier | -104, 28000 |
| A name that is no identifier | -919, 2E000 |
| A name in use | -919, 08002 |
| A server that cannot be reached | -919, 08001 |
| A server that refuses | -919, 08004 |
| No such connection, or no current one | -919, 08003 |
| DISCONNECT of a connection in a transaction | -917, 25000 |
| A connection that fails to end cleanly | a completion of 01002, a warning |

Each cites its rule of ISO/IEC 9075:1992 §15, as turborel-client's
does.

## EXAMPLES

```python
from turborel.client import Agent, Trust, connect

agent = Agent(lambda server, user: connect(("127.0.0.1", 7422), user or "ANN", Trust()))
try:
    agent.query("CONNECT TO db1")
except Exception as e:
    print(e.sqlcode, e.sqlstate, e.message, e.position)
try:
    agent.query("VALUES 1")
except Exception as e:
    print(e.sqlstate, e.message, e.rule)
```

```text
-102 2A000 expected a <literal>, found DB1 11
08003 there is no current connection ISO/IEC 9075:1992 §15.3 GR9
```

## SEE ALSO

[Pipelines and Pools](../user/08-pipelines-and-pools.md), the chapter;
[Connections](21-connections.md).
