# Settings

[Contents](README.md)

A program may leave where its servers are, as whom it connects and how,
to settings from outside it: a `turborel://` URI, a section of a service
file, the environment's TURBOREL_ variables, and a password file. This
chapter connects by settings with the low-level client,
`turborel.client`.

## A URI

`Settings.from_uri` reads a connection URI and the layers under it;
`connect` connects as they say. A URI names the user, a password, the
servers and settings, each part percent-encoded.

```python
from urllib.parse import quote

from turborel.client import Settings

secret = quote("ann's secret", safe="")
settings = Settings.from_uri(
    f"turborel://ANN:{secret}@127.0.0.1:7422/?application_name=ledger"
)
conn = settings.connect()
print(type(conn.target).__name__, conn.authorization)
conn.terminate()
```

```text
Tls ANN
```

A password is proved by SCRAM-SHA-256; with none, the client certificate
the settings name, else trust. By default the connection asks the
server for TLS and goes on without it if the server takes none, so this
one is over TLS. A Unix socket is named by its path, percent-encoded,
as `turborel://ANN@%2Frun%2Fturborel.sock/`, and an IPv6 address in
brackets.

## Where settings come from

Each setting is taken from the first of four layers that has it: the
program's options, or its URI's; the section of the service file that
the setting `service` names; the environment; the defaults. The
program gives its options as an `Options`, or a URI as
`Options.from_uri`. [Appendix C](../appendix/c-settings.md) lists every
setting, its variable and its default.

```python
from turborel.client import Options, Settings

options = Options().set("host", "db1,db2:7500").set("target", "read-write")
laid = Settings.resolve_in(
    options, {"TURBOREL_USER": "ann", "TURBOREL_PORT": "7000"}.get
)
print(laid.hosts, laid.user, laid.target.value)
```

```text
(Tcp(host='db1', port=7000), Tcp(host='db2', port=7500)) ann read-write
```

`Settings.resolve` reads the process's environment; `resolve_in` reads
it through a function the program gives, here a dict's `get`. A
variable set but empty gives nothing. A setting that cannot be read, a
service file that cannot be read or has no such section, or no user at
all is refused with SQLSTATE 08001.

A service file, `~/.turborel_service.conf` unless `service_file` names
another, holds sections of settings:

```text
# The ledger's servers.
[ledger]
host = db1,db2
port = 7422
user = ann
target = read-write
```

A password file, `~/.turborel_pass` unless `passfile` names another,
holds lines `host:port:user:password`, `*` matching anything and `\`
taking the character after it as it is; the first line that matches the
server and the user is taken. A Unix socket is matched by its path and
port 7422. The file is read only if it is a regular file; it should be
readable by its owner alone.

## Several servers

Settings may name several servers. They are tried in the order given,
or, with `load_balance=random`, in an order drawn at random for each
connection; each address a name resolves to is tried in turn, each step
within `connect_timeout`, 30 seconds by default. A server that cannot
be reached, refuses the user or is not of the role asked is passed for
the next. With none kept, the failure names each address and why, with
SQLSTATE 08001, or 28000 if the last refused the user.

`target=read-write` keeps only a server that takes changes, a server
alone or its group's primary; `target=read-only` only a replica that
follows its group. A server tells its role by the session status
SERVER_READ_ONLY; `role(conn)` gives it, as a connection's session sees
it.

```python
from turborel.client import Settings, role

try:
    Settings.from_uri(
        f"turborel://ANN:{secret}@127.0.0.1:7422/?target=read-only"
    ).connect()
except Exception as e:
    print(e.sqlstate, e.message)
conn = settings.connect()
print(role(conn).value)
conn.terminate()
```

```text
08001 the server is read-write, and read-only is asked
read-write
```

## TLS and channel binding

`tls_mode` says how a connection over TCP uses TLS: `disable`, never;
`prefer`, TLS if the server takes it, else plain TCP; `require`, TLS or
no connection; `verify-ca`, the server's certificate signed by an
authority `tls_roots` or the platform trusts; `verify-full`, that and
of `server_name`, else the host's. `prefer` and `require` keep out an
eavesdropper but not a server in the middle. A Unix socket or a named
pipe takes no TLS whatever the mode. A password is never sent over
plain TCP: settings that would are refused with SQLSTATE 28000.

`channel_binding` says whether SCRAM binds its exchange to the TLS
connection: `disable`, `prefer`, or `require`, which refuses, before
the login, settings that cannot bind, with SQLSTATE 28000. The driver
binds by the certificate the server presented, `tls-server-end-point`.

```python
try:
    Settings.from_uri(
        f"turborel://ANN:{secret}@127.0.0.1:7422/?tls_mode=disable"
    ).connect()
except Exception as e:
    print(e.sqlstate)
```

```text
28000
```

The connections one `Settings` makes share one SCRAM key cache, so each
after the first skips the derivation of the password's keys.

## See also

[Settings](../client/26-settings.md), the reference page;
[Appendix C: Settings](../appendix/c-settings.md);
[Connecting](02-connecting.md).
