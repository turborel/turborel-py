# Settings

[Contents](README.md)

## NAME

`turborel.client.Settings`, `Options`: connection settings from outside
the program, and connecting by them.

## SYNOPSIS

```python
Settings.from_uri(uri) -> Settings
Settings.resolve(options=None) -> Settings
Settings.resolve_in(options, variable) -> Settings
settings.connect() -> Connection
settings.password_for(host) -> str | None

Options(values=None)
Options.from_uri(uri) -> Options
options.set(key, value) -> Options | options.get(key) | options.over(lower)
Options.environment(variable) -> Options

role(connection) -> Role
TlsMode, TargetRole, LoadBalance, ChannelBinding, Role, TlsFiles
KEYS, ENVIRONMENT, SCHEME, DEFAULT_HOST, DEFAULT_SERVICE_FILE, DEFAULT_PASSFILE
```

## DESCRIPTION

**Options.** An `Options` is a layer of settings, each by one of the
names of `KEYS`. `set` refuses a name no setting has. `over` lays one
layer over another, each setting taken from the upper where it has it.
`Options.environment` reads each variable of `ENVIRONMENT` through
`variable`, an empty one giving nothing. `from_uri` reads a URI:

```text
turborel://[<user>[:<password>]@][<host>[:<port>][,<host>[:<port>]]...][/][?<key>=<value>[&<key>=<value>]...]
```

its user, password, hosts and values percent-encoded, an IPv6 address
in brackets, a path a Unix socket, or on Windows a named pipe. A URI of
another scheme, a path, a key no setting has or a pair without `=` is
refused.

**Settings.** `resolve_in` lays the program's options over the section
of the service file the setting `service` names, `service_file` or
`~/.turborel_service.conf`, over the environment, over the defaults,
and reads them into a `Settings`: `hosts`, each a `Tcp` or `Local`
target; `user`; `password`; `tls_mode`; `channel_binding`;
`application_name`; `connect_timeout`, in seconds, None for no limit;
`passfile`, `~/.turborel_pass` by default; `target`; `load_balance`;
`tls`, a `TlsFiles` of `roots`, `system_roots`, `certificate`, `key`
and `server_name`; and `key_cache`. `resolve` reads the process's
environment; `from_uri` resolves a URI. Its `repr` never shows the
password. `password_for` gives the settings' password, else the
password file's for a host, its port, 7422 for a local socket, and the
user, the file read only if it is a regular file, or a link to one.

**The service file.** Sections `[<name>]`, then lines `<key> =
<value>`; `#` comments and blank lines skipped. A section cannot set
`service` or `service_file`. A malformed line is refused, its file and
line named.

**The password file.** Lines `<host>:<port>:<user>:<password>`; a field
`*` matches anything; `\` takes the character after it as it is; `#`
begins a comment; a line of fewer fields is skipped; the first line
that matches is taken.

**Connecting.** `connect` tries each host, in order or, with
`LoadBalance.RANDOM`, in an order drawn for each connection, and each
address a name resolves to, every step within `connect_timeout`. Over
TCP it uses TLS as `tls_mode` says: `DISABLE`; `PREFER`, TLS, else
plain TCP, connecting again after a failed handshake; `REQUIRE`;
`VERIFY_CA`, the server's certificate checked against the authorities
trusted; `VERIFY_FULL`, and its name against `server_name`, else the
host's. Over a local socket, no TLS. It proves a password by
SCRAM-SHA-256, bound by the server's certificate as `channel_binding`
says; with none, the certificate `tls.certificate` names, presented
with `tls.key`; else trust. It sends `application_name` as the
connection attribute `application`, and asks every capability but
compression. A server unreachable, refusing the user, or not of the
role `target` asks is passed for the next; the first kept is given.
The connections one `Settings` makes share its `key_cache`.

**Roles.** `role` gives a connection's server's `Role`, `READ_WRITE`,
`READ_ONLY` or `UNKNOWN`: as SERVER_READ_ONLY last told it, else by a
query of INFORMATION_SCHEMA.REPLICAS, run as its own transaction; a
server alone, which has no REPLICAS, is read-write, and a replica whose
row the session cannot see unknown.

## ERRORS

| Condition | SQLCODE, SQLSTATE |
|---|---|
| A setting or URI that cannot be read, a service file unread or without the section, no user, a server not of the role asked | -919, 08001 |
| No server kept, of several | -919, 08001, naming each address and why; 28000 if the last refused the user |
| Of one server tried, its own failure | as it failed |
| A password over plain TCP; `channel_binding=require` of settings that cannot bind | -919, 28000 |
| A TLS file that cannot be read, a certificate without its key, a verifying mode with no authority trusted | -919, 08006 |

## EXAMPLES

```python
from turborel.client import Options, Settings

options = Options.from_uri("turborel://ann@db1:7000,db2/?target=read-write")
settings = Settings.resolve_in(options, {"TURBOREL_PORT": "7500"}.get)
print(settings.hosts)
print(settings.user, settings.target)
```

```text
(Tcp(host='db1', port=7000), Tcp(host='db2', port=7500))
ann TargetRole.READ_WRITE
```

## SEE ALSO

[Settings](../user/09-settings.md), the chapter;
[Appendix C: Settings](../appendix/c-settings.md);
[Connections](21-connections.md).
