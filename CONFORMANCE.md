# Conformance

This file is the parity matrix: what turborel-py implements of the native
protocol, version 1, and of what turborel-client does. Its rows are the
same in every turborel driver, taken in the order of turborel's
documents: doc/client/05-protocol.md (`PROTOCOL`), then
doc/client/02-library.md and 02-library-connections.md (`CLIENT`). Each
row names the section it comes from, by its heading. Where the page and
turborel's code differ, the code is right, and the row says so.

A row is **done** once it is implemented and tested, its tests citing
its section (RULES.md R-TRACE-1); until then it is **not yet**. The
driver is done when every row is (TODO.md, M8). The choices the driver
makes where turborel-client leaves them to a language are recorded in
RULES.md and named in the row.

Contents: [Frames and fields](#frames-and-fields) ·
[Data types](#data-types) · [Values](#values) · [The tail](#the-tail) ·
[Opening a connection](#opening-a-connection) ·
[Capabilities](#capabilities) · [Requests](#requests) ·
[Replies](#replies) · [Errors and notices](#errors-and-notices) ·
[The client library](#the-client-library) ·
[Settings, pipelines and pools](#settings-pipelines-and-pools) ·
[The standard API](#the-standard-api)

---

## Frames and fields

| Row | Section | Status |
|---|---|---|
| Frame header: kind `u8`, length `u32` little-endian, five bytes | `[PROTOCOL Frames]` | done |
| A kind not known, a body cut short, or bytes left over fail the connection (-919, 08006) | `[PROTOCOL Frames]` | not yet |
| Replies of up to 16 MiB taken by default, the limit settable; a longer one fails the connection | `[PROTOCOL Frames]` | not yet |
| Compressed frame `z`: kind, length, a zlib stream, inflated within the length bound | `[PROTOCOL Compressed frames]` | not yet |
| A `z` within a `z`, one that inflates to another length, or one not granted fails the connection | `[PROTOCOL Compressed frames]` | not yet |
| The client's own compression threshold | `[PROTOCOL Compressed frames]` | not yet |
| Fields `u8`, `u32`, `u64`, `i128`, flag, string, bytes, list, strings, key | `[PROTOCOL Values and fields]` | not yet |
| A count larger than what follows fails as the body runs out, reserving nothing | `[PROTOCOL Values and fields]` | not yet |
| Composite fields: row, column, parameter, failure | `[PROTOCOL Composite fields]` | not yet |

## Data types

| Row | Section | Status |
|---|---|---|
| 1 CHARACTER: length, units | `[PROTOCOL Data types]` | not yet |
| 2 exact numeric: precision, scale | `[PROTOCOL Data types]` | not yet |
| 3 approximate numeric: precision | `[PROTOCOL Data types]` | not yet |
| 4 a plug-in's type: name, parameters; one not known read by name | `[PROTOCOL Data types]` | not yet |
| 5 CHARACTER VARYING: length, units | `[PROTOCOL Data types]` | not yet |
| 6 BINARY: length | `[PROTOCOL Data types]` | not yet |
| 7 BINARY VARYING: length | `[PROTOCOL Data types]` | not yet |
| 8 DATE: precision | `[PROTOCOL Data types]` | not yet |
| 9 TIME: precision | `[PROTOCOL Data types]` | not yet |
| 10 TIME WITH TIME ZONE: precision | `[PROTOCOL Data types]` | not yet |
| 11 TIMESTAMP: precision | `[PROTOCOL Data types]` | not yet |
| 12 TIMESTAMP WITH TIME ZONE: precision | `[PROTOCOL Data types]` | not yet |
| 13 INTERVAL: start and end fields, leading and fractional precision | `[PROTOCOL Data types]` | not yet |
| 14 BOOLEAN | `[PROTOCOL Data types]` | not yet |
| 15 DECFLOAT: precision | `[PROTOCOL Data types]` | not yet |
| 16 array: maximum cardinality, element type | `[PROTOCOL Data types]` | not yet |
| 17 row: each field's name and type | `[PROTOCOL Data types]` | not yet |
| 18 CHARACTER LARGE OBJECT: length `u64`, units | `[PROTOCOL Data types]` | not yet |
| 19 BINARY LARGE OBJECT: length `u64`, units | `[PROTOCOL Data types]` | not yet |
| 22 multiset: element type | `[PROTOCOL Data types]` | not yet |
| 23 structured type: schema, name, proper supertypes | `[PROTOCOL Data types]` | not yet |
| 24 reference type: referenced type, scope | `[PROTOCOL Data types]` | not yet |
| 25 JSON | `[PROTOCOL Data types]` | not yet |
| 26 XML: primary and secondary modifiers, XMLSCHEMA's schema, namespace and element | `[PROTOCOL Data types]` | not yet |
| 27 UUID, no parameters (turborel's RULES.md D184, `protocol/src/fields.rs`; not on the page yet) | `[PROTOCOL Data types]` | not yet |

## Values

| Row | Section | Status |
|---|---|---|
| 0 null | `[PROTOCOL Values]` | not yet |
| 1 character string, of CHARACTER and CHARACTER VARYING | `[PROTOCOL Values]` | not yet |
| 2 exact number: units `i128`, scale `u32`, as `decimal.Decimal` or `int` | `[PROTOCOL Values]` | not yet |
| 3 approximate number: IEEE 754 double, NaN and -0.0 kept | `[PROTOCOL Values]` | not yet |
| 4 a plug-in's value: type name, text, bytes | `[PROTOCOL Values]` | not yet |
| 6 binary string | `[PROTOCOL Values]` | not yet |
| 8 date, as a timestamp | `[PROTOCOL Values]` | not yet |
| 9 time, as a timestamp | `[PROTOCOL Values]` | not yet |
| 11 timestamp: zoned, precision, displacement -12:59 to +14:00, microseconds in UTC | `[PROTOCOL Values]` | not yet |
| 13 interval: qualifier, then months or microseconds, each qualifier | `[PROTOCOL Values]` | not yet |
| 14 truth value; unknown as null | `[PROTOCOL Values]` | not yet |
| 15 decimal floating point: coefficient `i128`, exponent | `[PROTOCOL Values]` | not yet |
| 16 array, nested | `[PROTOCOL Values]` | not yet |
| 17 row | `[PROTOCOL Values]` | not yet |
| 20 large object, whole: kind, octets | `[PROTOCOL Values]` | not yet |
| 21 large object, by locator: kind, locator, octets, characters | `[PROTOCOL Values]` | not yet |
| 22 multiset, in no set order | `[PROTOCOL Values]` | not yet |
| 23 structured value: most specific type, attributes | `[PROTOCOL Values]` | not yet |
| 24 reference | `[PROTOCOL Values]` | not yet |
| 25 JSON: turborel's RULES.md D89 binary tree, every node, decoded and encoded (the page says only "its stored form") | `[PROTOCOL Values]` | not yet |
| 26 XML: its serialization as CONTENT | `[PROTOCOL Values]` | not yet |
| 27 UUID: bytes, a count of 16 then the octets (turborel's RULES.md D184; not on the page yet) | `[PROTOCOL Values]` | not yet |

## The tail

| Row | Section | Status |
|---|---|---|
| Tags in increasing order; one not taken or not past the last fails the connection | `[PROTOCOL The tail]` | not yet |
| 1 attributes: at most 32, names 1 to 64 bytes, values at most 1024 | `[PROTOCOL The tail]` | not yet |
| 2 multi | `[PROTOCOL The tail]` | not yet |
| 3 cursor | `[PROTOCOL The tail]` | not yet |
| 4 position | `[PROTOCOL The tail]` | not yet |
| 5 more | `[PROTOCOL The tail]` | not yet |
| 6 rows | `[PROTOCOL The tail]` | not yet |
| 7 to 15 severity, detail, hint, context, schema, table, column, data type, constraint | `[PROTOCOL The tail]` | not yet |
| 16 generated | `[PROTOCOL The tail]` | not yet |
| 17 conditions, each a failure as bytes | `[PROTOCOL The tail]` | not yet |
| 18 time: total, queued, locks | `[PROTOCOL The tail]` | not yet |

## Opening a connection

| Row | Section | Status |
|---|---|---|
| Hello, the Challenge and Answer steps, Statuses, Ready | `[PROTOCOL Opening a connection]` | not yet |
| Mechanism `trust` | `[PROTOCOL Mechanisms]` | not yet |
| Mechanism `password`, only over TLS, a Unix socket or a named pipe | `[PROTOCOL Mechanisms]` | not yet |
| Mechanism `certificate` | `[PROTOCOL Mechanisms]` | not yet |
| Mechanism `scram-sha-256`, RFC 5802 and RFC 7677 | `[PROTOCOL Mechanisms]` | not yet |
| Mechanism `scram-sha-256-plus`, by `tls-server-end-point` (RULES.md D1) | `[PROTOCOL Mechanisms]` | not yet |
| Status names AUTHORIZATION, SCHEMA, READ_ONLY, SERVER_VERSION, and SERVER_READ_ONLY, CATALOG and OWNER (turborel's `server/src/native/status.rs`; the last three not on the page yet) | `[PROTOCOL Status 'T']` | not yet |

## Capabilities

| Row | Section | Status |
|---|---|---|
| `notices` | `[PROTOCOL Capabilities]` | not yet |
| `status` | `[PROTOCOL Capabilities]` | not yet |
| `diagnostics` | `[PROTOCOL Capabilities]` | not yet |
| `describe` | `[PROTOCOL Capabilities]` | not yet |
| `cursors` | `[PROTOCOL Capabilities]` | not yet |
| `ping` | `[PROTOCOL Capabilities]` | not yet |
| `reset` | `[PROTOCOL Capabilities]` | not yet |
| `change-user` | `[PROTOCOL Capabilities]` | not yet |
| `query-attributes` | `[PROTOCOL Capabilities]` | not yet |
| `connection-attributes` | `[PROTOCOL Capabilities]` | not yet |
| `multi-statement` | `[PROTOCOL Capabilities]` | not yet |
| `compression` | `[PROTOCOL Capabilities]` | not yet |
| `commit-position` | `[PROTOCOL Capabilities]` | not yet |
| `copy` | `[PROTOCOL Capabilities]` | not yet |
| `row-counts` | `[PROTOCOL Capabilities]` | not yet |
| `generated-values` | `[PROTOCOL Capabilities]` | not yet |
| `fetch-ends` | `[PROTOCOL Capabilities]` | not yet |
| `conditions` | `[PROTOCOL Capabilities]` | not yet |
| A request or tail field of a capability not granted is never sent | `[PROTOCOL Capabilities]` | not yet |

## Requests

| Row | Section | Status |
|---|---|---|
| Hello `H` | `[PROTOCOL Hello 'H']` | not yet |
| Answer `A` | `[PROTOCOL Answer 'A']` | not yet |
| Query `Q` | `[PROTOCOL Query 'Q']` | not yet |
| Prepare `P` | `[PROTOCOL Prepare 'P']` | not yet |
| Execute `E` | `[PROTOCOL Execute 'E']` | not yet |
| Fetch `F` | `[PROTOCOL Fetch 'F']` | not yet |
| Close `C` | `[PROTOCOL Close 'C']` | not yet |
| Deallocate `D` | `[PROTOCOL Deallocate 'D']` | not yet |
| Lob `L`: read, create, append, free, hold | `[PROTOCOL Lob 'L']` | not yet |
| Cancel `Z` | `[PROTOCOL Cancel 'Z']` | not yet |
| Terminate `X` | `[PROTOCOL Terminate 'X']` | not yet |
| Describe `Y` | `[PROTOCOL Describe 'Y']` | not yet |
| Ping `G` | `[PROTOCOL Ping 'G']` | not yet |
| Reset `W` | `[PROTOCOL Reset 'W']` | not yet |
| ChangeUser `U` | `[PROTOCOL ChangeUser 'U']` | not yet |
| CopyIn `I` | `[PROTOCOL CopyIn 'I']` | not yet |
| CopyData `J` | `[PROTOCOL CopyData 'J']` | not yet |
| CopyEnd `N` | `[PROTOCOL CopyEnd 'N']` | not yet |

## Replies

| Row | Section | Status |
|---|---|---|
| Challenge `C` | `[PROTOCOL Challenge 'C']` | not yet |
| Ready `R` | `[PROTOCOL Ready 'R']` | not yet |
| Prepared `P` | `[PROTOCOL Prepared 'P']` | not yet |
| Description `D` | `[PROTOCOL Description 'D']` | not yet |
| Rows `B` | `[PROTOCOL Rows 'B']` | not yet |
| Suspended `S` | `[PROTOCOL Suspended 'S']` | not yet |
| Complete `K` | `[PROTOCOL Complete 'K']` | not yet |
| Error `E` | `[PROTOCOL Error 'E']` | not yet |
| Lob `L`: data, locator | `[PROTOCOL Lob 'L']` | not yet |
| Notice `N` | `[PROTOCOL Notice 'N']` | not yet |
| Status `T` | `[PROTOCOL Status 'T']` | not yet |
| Pong `G` | `[PROTOCOL Pong 'G']` | not yet |
| Replies in their fixed order, as the conversations show | `[PROTOCOL Conversations]` | not yet |
| The worked example, byte for byte | `[PROTOCOL A worked example]` | not yet |

## Errors and notices

| Row | Section | Status |
|---|---|---|
| Severities ERROR, FATAL, WARNING, NOTICE | `[PROTOCOL Errors and notices]` | not yet |
| Conditions told one way: in Complete with `conditions`, else as Notices | `[PROTOCOL Errors and notices]` | not yet |
| SQLSTATEs 01T01 and TBR01 | `[PROTOCOL Errors and notices]` | not yet |
| An Error of class 08 but 08003, or of class 28 at login, ends the connection | `[PROTOCOL Error 'E']` | not yet |

## The client library

| Row | Section | Status |
|---|---|---|
| Connect over TCP, a Unix socket, or on Windows the named pipe `\\.\pipe\turborel` | `[CLIENT Connecting]` | not yet |
| SCRAM, over TLS bound to the channel; `in_the_clear` for a server that allows it | `[CLIENT Connecting]` | not yet |
| Password, certificate and trust mechanisms | `[CLIENT Connecting]` | not yet |
| Secrets refused over plain TCP before connecting (28000) | `[CLIENT Connecting]` | not yet |
| TLS trusting given authorities, the platform's on request | `[CLIENT Connecting]` | not yet |
| Terminate, waiting at most 60 seconds | `[CLIENT Connecting]` | not yet |
| Timeouts: connect 30 seconds, read unlimited by default, settable | `[CLIENT Timeouts]` | not yet |
| The longest reply taken settable | `[CLIENT Timeouts]` | not yet |
| Query, giving rows or a completion; failures with SQLCODE, SQLSTATE, message, rule and position | `[CLIENT Running statements]` | not yet |
| Streamed query, a batch at a time | `[CLIENT Running statements]` | not yet |
| `in_transaction` | `[CLIENT Running statements]` | not yet |
| Cancel from another thread, giving up after 10 seconds | `[CLIENT Running statements]` | not yet |
| Autocommit, through `ends` | `[CLIENT Running statements]` | not yet |
| Prepare, execute, parameters, columns | `[CLIENT Prepared statements]` | not yet |
| Open a cursor, fetch, close, deallocate | `[CLIENT Prepared statements]` | not yet |
| Large objects by locator: read in 256 KiB chunks by octets or characters | `[CLIENT Large objects]` | not yet |
| Free and hold a locator | `[CLIENT Large objects]` | not yet |
| Create a large object a piece at a time, a character split between writes | `[CLIENT Large objects]` | not yet |
| XML values: text sent and read | `[CLIENT XML values]` | not yet |
| UUIDs: octets and text, both ways | `[CLIENT UUIDs]` | not yet |
| Import from a source of records; CSV and tab-separated text | `[CLIENT Importing]` | not yet |
| Import's batches, skipping, and its error of where and why | `[CLIENT Importing]` | not yet |
| Every capability asked for but compression; an offer of the program's; connection attributes; what was granted | `[CLIENT What a connection asks for]` | not yet |
| A method needing a capability not granted fails before sending | `[CLIENT What a connection asks for]` | not yet |
| Settings told by Status, with no round trip | `[CLIENT What the server tells]` | not yet |
| Notices: a handler, or the last 64 kept | `[CLIENT What the server tells]` | not yet |
| Conditions of the last statement | `[CLIENT What the server tells]` | not yet |
| Rows affected, generated values, server time, commit position | `[CLIENT What the server tells]` | not yet |
| A failure's diagnostics | `[CLIENT What the server tells]` | not yet |
| Under autocommit, a cursor ending its transaction with `fetch-ends` | `[CLIENT What the server tells]` | not yet |
| Ping, reset, change user | `[CLIENT Controlling the session]` | not yet |
| Query attributes | `[CLIENT Controlling the session]` | not yet |
| Several statements in one request | `[CLIENT Controlling the session]` | not yet |
| Describe a statement; numbered cursors; describe a cursor | `[CLIENT Controlling the session]` | not yet |
| Copy in: send, finish, abandon when dropped; copy rows from an iterable | `[CLIENT Copying and exporting]` | not yet |
| Export as CSV, or as native frames read back with every value as it was | `[CLIENT Copying and exporting]` | not yet |
| The SQL-agent: CONNECT, SET CONNECTION, DISCONNECT, by a connector | `[CLIENT The SQL-agent]` | not yet |

## Settings, pipelines and pools

| Row | Section | Status |
|---|---|---|
| Connect by settings, the mechanism chosen by what they give | `[CLIENT Connecting by settings]` | not yet |
| Every setting of the table, with its default | `[CLIENT Where settings come from]` | not yet |
| Layers: the program's, the service file's section, the environment, the defaults | `[CLIENT Where settings come from]` | not yet |
| TURBOREL_* variables, an empty one giving nothing; an environment of the program's | `[CLIENT Where settings come from]` | not yet |
| Settings refused with 08001; `application_name` sent as `application` | `[CLIENT Where settings come from]` | not yet |
| The `turborel://` URI, percent-encoded, IPv6 in brackets, sockets by path; others refused | `[CLIENT The connection URI]` | not yet |
| The service file: sections, comments, malformed lines refused by file and line | `[CLIENT The service file]` | not yet |
| The password file: fields, `*`, escapes, comments, the first match; sockets by path | `[CLIENT The password file]` | not yet |
| Several hosts, in order or `load_balance=random`; each address within the timeout | `[CLIENT Several servers]` | not yet |
| `target` read-write and read-only, by SERVER_READ_ONLY or INFORMATION_SCHEMA.REPLICAS | `[CLIENT Several servers]` | not yet |
| `tls_mode` disable, prefer, require, verify-ca, verify-full; prefer falling back | `[CLIENT TLS by mode]` | not yet |
| `channel_binding` disable, prefer, require | `[CLIENT TLS by mode]` | not yet |
| Pipelines: queued requests, outcomes in order, a 64 KiB window | `[CLIENT Pipelines]` | not yet |
| Skip on error, by savepoints | `[CLIENT Pipelines]` | not yet |
| Pools: PoolConfig's defaults, max, idle and lifetime limits, wait | `[CLIENT Pools]` | not yet |
| A pool's check by Ping, its return by Reset; ROLLBACK and a pipeline where neither is granted | `[CLIENT Pools]` | not yet |
| A pool of settings or of any source; no thread of its own | `[CLIENT Pools]` | not yet |
| The SCRAM key cache: 64 entries, keyed by salt, iterations and a keyed tag; dropped on a failed login | `[CLIENT The SCRAM key cache]` | not yet |
| One cache shared by every connection settings make | `[CLIENT The SCRAM key cache]` | not yet |

## The standard API

The driver's own rows, beyond the matrix every driver shares (RULES.md
D2).

| Row | Where | Status |
|---|---|---|
| PEP 249's exceptions, each carrying SQLCODE, SQLSTATE and message | RULES.md D2, D7 | done |
| `apilevel` "2.0" and `paramstyle` "qmark" | RULES.md D2 | done |
| `connect`, `threadsafety`, the connection and cursor objects, type objects and constructors | RULES.md D2 | not yet |
| `turborel.aio`, the asyncio interface | RULES.md D2 | not yet |
