# Connections

[Contents](README.md)

## NAME

`turborel.client`: connecting to a server, and the connection a program
then holds.

## SYNOPSIS

```python
connect(address, user, mechanism) -> Connection
connect_local(path, user, mechanism) -> Connection
connect_tls(address, context, user, mechanism, server_name=None) -> Connection
connect_to(target, user, mechanism, timeouts=None, offer=None) -> Connection
Connection.open(socket_or_file, user, mechanism, offer=None) -> Connection
Connection.open_within(sock, user, mechanism, timeouts, offer=None) -> Connection

Tcp(host, port=7422) | Local(path) | Tls(host, context, port=7422, server_name=None)
Trust() | Password(password) | Certificate()
Scram(password, *, in_the_clear=False, channel_binding=ChannelBinding.PREFER, cache=None)
Timeouts(connect=30.0, read=None)
Offer(capabilities=..., attributes=(), compress_from=1024)
trusting(file) | roots(file=None, *, platform=False) | presenting(file, chain, key)
KeyCache()
```

## DESCRIPTION

**Connecting.** `connect` connects over TCP to `address`, a host on port
7422 or a `(host, port)` pair; `connect_local` over a Unix socket, or on
Windows the named pipe `\\.\pipe\turborel` or another; `connect_tls` over
TLS, the server's certificate checked by the `ssl.SSLContext` given and
its name by `server_name`, the host's by default; `connect_to` to a
`Target`, with timeouts and an offer of the program's. `Connection.open`
logs in over a stream the program opened, which bounds its own waits;
over a TLS socket the program binds SCRAM to it first,
`mechanism.bind(tls_channel(sock))`. `Connection.open_within` logs in
over a socket the program opened, bounded as `timeouts` say: each step
of the login by `connect`, each wait after it by `read`, which
`set_read_timeout` then changes.

**Mechanisms.** `Trust` asks the server to trust the user as it names
itself, which it does of a client of its own machine where
SERVER.TRUST_LOCAL is ON. `Password` sends the password whole, and
`Scram` proves it by SCRAM-SHA-256, or SCRAM-SHA-256-PLUS over TLS, bound
by the certificate the server presented; both are refused over plain TCP
before connecting, unless `Scram` is made `in_the_clear`. `Certificate`
proves the user by the TLS client certificate `presenting` presents.
`channel_binding` says whether SCRAM binds the TLS channel: `DISABLE`,
`PREFER` where the connection has a binding, or `REQUIRE`, which refuses
an exchange not bound.

**TLS.** `trusting(file)` trusts the authorities of a PEM file alone;
`roots(file, platform=True)` the platform's too, or alone with no file,
read from SSL_CERT_FILE and SSL_CERT_DIR where either is set;
`presenting(file, chain, key)` presents a certificate chain and its key.
Each offers TLS 1.2 and 1.3 and checks the server's certificate and name.

**The SCRAM key cache.** A `KeyCache` given to `Scram` keeps the keys a
password derived by PBKDF2, so a later login of the same salt and
iterations skips the derivation. An entry is found by the salt, the
iterations and a tag of the password under a random secret of the
cache's own; it holds at most 64 (`KEY_CACHE_ENTRIES`), the oldest
dropped first, drops an entry when a login that used it fails, and lives
in the process's memory alone. `lookups()` gives its hits and misses.

**Timeouts.** `Timeouts.connect` bounds connecting, beginning TLS and each
step of the login, 30 seconds by default; `Timeouts.read` each read or
write after, no limit by default. A wait that runs out loses the
connection. A named pipe is bounded only as it is opened.

**What a connection asks for.** By default every capability but
compression. `Offer.none()` asks for none, `compressed()` adds
compression, and `attribute(name, value)` a connection attribute, which
the server shows in INFORMATION_SCHEMA.CONNECTION_ATTRIBUTES.

**The connection.**

| Member | What |
|---|---|
| `authorization`, `server` | the session's user and the server's product, as Ready told them |
| `target` | where it reached its server, or None for `open` |
| `granted` | the capabilities granted, in Ready's order |
| `setting(name)`, `settings()` | a session setting, or all, as the server last told them |
| `set_notice_handler(handler)`, `take_notices()` | notices handed to a handler as they come, or the last 64 kept and taken |
| `in_transaction` | whether the session's transaction is active |
| `autocommit` | whether each statement is its own transaction |
| `read_timeout`, `set_read_timeout(seconds)` | the read timeout, changed |
| `set_max_body(bytes)` | the longest reply's body taken, 16 MiB by default |
| `canceller()` | what cancels its statements from another thread |
| `ping()` | whether the server and the connection are alive |
| `reset()` | the session as it was at login, its user kept |
| `change_user(user, mechanism)` | the connection authenticated again as `user` |
| `query(sql)` and the rest | statements, prepared statements and cursors ([Statements and Cursors](22-statements.md)) |
| `terminate()` | the session ended, its transaction as SESSION.COMMIT_AT_END says; a notice or status before a failing commit's failure read past, that failure raised; waiting for the close at most the read timeout, else 60 seconds, or over a stream given to `open` as its maker set it |
| `close()` | the connection closed, the session not ended first |
| `is_lost` | whether it is lost, every call then giving its failure |

`Canceller.cancel(within=10.0)` sends the session's cancel key on a
connection of its own and waits for the server to close it.

## ERRORS

| Condition | SQLCODE, SQLSTATE |
|---|---|
| A password, or SCRAM, over plain TCP, before connecting | -919, 28000 |
| A wrong user or password, or SCRAM's proof refused either way | -919, 28000 |
| A server that cannot be reached, a TLS handshake that fails, a wait that runs out, a reply malformed or too long | -919, 08006 |
| A method needing a capability the server did not grant, before it sends anything | -919, 08006 |
| A statement cancelled | -920, TB920 |

A failure of class 08 but 08003, or of class 28 at login, loses the
connection; so does any failure of its stream.

## EXAMPLES

```python
from turborel.client import KeyCache, Scram, connect_local

cache = KeyCache()
connect_local(
    "/tmp/trl-doc.sock", "ANN", Scram("ann's secret", cache=cache)
).terminate()
connect_local(
    "/tmp/trl-doc.sock", "ANN", Scram("ann's secret", cache=cache)
).terminate()
print(cache.lookups())
```

```text
(1, 1)
```

```python
from turborel.client import Offer, Tcp, Trust, connect_to

conn = connect_to(Tcp("127.0.0.1", 17431), "ANN", Trust(), offer=Offer.none())
print(conn.granted)
```

```text
()
```

## SEE ALSO

[Connecting](../user/02-connecting.md), the chapter;
[The Native Protocol](https://github.com/turborel/turborel/blob/main/doc/client/05-protocol.md);
[The Client Library](https://github.com/turborel/turborel/blob/main/doc/client/02-library.md),
turborel-client's.
