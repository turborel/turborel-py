# Connecting

[Contents](README.md)

A program connects to a Turborel server, `turboreld`, over TCP, a Unix
socket, or on Windows a named pipe; or over TLS on the server's TCP port.
It names the user it connects as, and a mechanism that proves it. This
chapter connects with the low-level client, the module `turborel.client`;
the standard API's way of connecting, `turborel.connect`, comes at
milestone M7.

## A first connection

A server trusts a client of its own machine as the user it names, when
its operator sets SERVER.TRUST_LOCAL ON
([Users and Authentication](https://github.com/turborel/turborel/blob/main/doc/operator/05-users.md)).
The mechanism `Trust` asks for that.

```python
from turborel.client import Trust, connect

conn = connect(("127.0.0.1", 7422), "ann", Trust())
print(conn.server, conn.authorization)
conn.terminate()
```

```text
turborel 0.0.0 (alpha) ANN
```

A user name is read as an identifier, so `ann` connects as ANN. A host
alone, `connect("db.example", ...)`, is on port 7422. `terminate` ends the
session, its transaction committed or rolled back as SESSION.COMMIT_AT_END
says, ON by default.

## Proving a password

A password is proved by SCRAM-SHA-256: the password never travels, and
the server must prove it knows the user's verifier, or the connection is
refused.

```python
from turborel.client import Scram, connect_local

conn = connect_local("/run/turborel.sock", "ANN", Scram("ann's secret"))
```

An exchange overheard lets the password be guessed at leisure, so SCRAM
goes only over TLS, a Unix socket or a named pipe. Over plain TCP the
driver refuses before it connects, as it does `Password`, which sends the
password whole:

```python
from turborel.client import Password, connect

connect(("127.0.0.1", 7422), "ANN", Password("ann's secret"))
```

```text
turborel.OperationalError: password is sent only over TLS, a Unix socket or a named pipe, never over plain TCP
```

Its SQLSTATE is 28000. `Scram(password, in_the_clear=True)` sends SCRAM
over plain TCP all the same, to a server whose SERVER.SCRAM_WITHOUT_TLS
is ON. A wrong password is refused by the server, with SQLCODE -919 and
SQLSTATE 28000:

```text
turborel.OperationalError: the user or the password is wrong
```

## TLS

TLS begins on the server's TCP port. `trusting` makes a TLS context that
trusts the authorities of one PEM file, and checks the server's
certificate and name.

```python
from turborel.client import Scram, connect_tls, trusting

context = trusting("/etc/turborel/ca.pem")
conn = connect_tls("db.example", context, "ANN", Scram("ann's secret"))
```

Over TLS, SCRAM is SCRAM-SHA-256-PLUS, bound to the connection by the
certificate the server presented, so a server in the middle cannot relay
it. `roots(file, platform=True)` trusts the platform's authorities too,
or alone with no file; they are those of the files SSL_CERT_FILE and
SSL_CERT_DIR name, where either is set. `presenting(file, chain, key)`
presents a certificate chain and its key too, to log in by `Certificate`,
as the user the certificate's common name names.

## Timeouts

A connection waits 30 seconds to connect, begin TLS and take each step
of the login, and as long as a statement runs after. `connect_to` takes a
`Timeouts` of its own:

```python
from turborel.client import Tcp, Timeouts, Trust, connect_to

conn = connect_to(Tcp("127.0.0.1", 7422), "ANN", Trust(), Timeouts(connect=5, read=60))
print(conn.read_timeout)
```

```text
60
```

`set_read_timeout` changes the read timeout. A wait that runs out loses
the connection, with SQLSTATE 08006, saying the server did not answer in
time.

## What the server tells

The server tells a session its settings as it begins, and again as a
statement changes one. `setting` reads one, with no round trip:

```python
conn = connect(("127.0.0.1", 7422), "ANN", Trust())
print(conn.setting("SESSION.TIME_ZONE"), conn.setting("SERVER_READ_ONLY"))
```

```text
+00:00 NO
```

## Cancelling and ending

`canceller()` gives what cancels the statement a connection runs, from
another thread: its `cancel` opens a connection of its own and sends the
session's key, and the statement fails with SQLCODE -920 and SQLSTATE
TB920. `ping` asks whether the server and the connection are alive, with
no statement run; `terminate` ends the session.

The API Reference's page [Connections](../client/21-connections.md)
gives every function and method.
