# Appendix C: Settings

[Contents](README.md)

Every connection setting, by its name in `Options`, a URI's query and a
service file; the environment variable that gives it, if any; what it
says; and its default. [Settings](../user/09-settings.md) tells how the
layers are laid; the pool's settings come after.

| Setting | Variable | What | Default |
|---|---|---|---|
| `host` | TURBOREL_HOST | the servers, comma-separated, each `<name>`, `<name>:<port>`, `[<IPv6>]`, `[<IPv6>]:<port>`, or a path of a Unix socket or named pipe | `localhost` |
| `port` | TURBOREL_PORT | one port for every host, or one each, comma-separated | 7422 |
| `user` | TURBOREL_USER | the user to connect as | none: it must be given |
| `password` | TURBOREL_PASSWORD | the user's password | the password file's |
| `tls_mode` | TURBOREL_TLS_MODE | `disable`, `prefer`, `require`, `verify-ca` or `verify-full` | `prefer` |
| `channel_binding` | | `disable`, `prefer` or `require` | `prefer` |
| `application_name` | TURBOREL_APPLICATION_NAME | the program's name, sent as the connection attribute `application` | none |
| `connect_timeout` | TURBOREL_CONNECT_TIMEOUT | each step of connecting, in whole seconds; 0 for no limit | 30 |
| `service` | TURBOREL_SERVICE | the section of the service file to read | none |
| `service_file` | TURBOREL_SERVICE_FILE | the service file | `~/.turborel_service.conf` |
| `passfile` | TURBOREL_PASSFILE | the password file | `~/.turborel_pass` |
| `target` | | `any`, `read-write` or `read-only` | `any` |
| `load_balance` | | `disable` or `random` | `disable` |
| `tls_roots` | | a PEM file of the authorities trusted | none |
| `tls_system_roots` | | `true` to trust the platform's authorities too | `false` |
| `tls_certificate` | | a PEM file of the client's certificate chain, presented | none |
| `tls_key` | | a PEM file of its private key | none |
| `server_name` | | the name the server's certificate is checked against | the host's |

A section of a service file cannot set `service` or `service_file`.

## A pool's settings

The fields of `PoolConfig` ([Pools](../client/28-pools.md)), times in
seconds, None for no limit.

| Setting | What | Default |
|---|---|---|
| `max` | the most connections made at once, handed out and idle | 10 |
| `max_idle` | the most kept idle | 10 |
| `idle_timeout` | how long one may stay idle | 600, ten minutes |
| `max_lifetime` | how long one lives from when it was made | 3600, an hour |
| `wait` | how long `get` waits for one to come back | 30 |
| `check` | whether an idle one is checked to answer before it is handed out | `True` |
| `reset` | statements run, after the pool's own, as each comes back | none |
