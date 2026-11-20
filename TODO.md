# TODO

Open work, by milestone. Each item says what is missing. How the driver
is built is in [RULES.md](RULES.md), and what is implemented is in
[CONFORMANCE.md](CONFORMANCE.md), whose rows these milestones mark done.
Finished work leaves this file, and git keeps its history.

Code never cites this file (R-DOC-3).

[M1 Codec](#m1-codec) · [M2 Connect](#m2-connect) ·
[M3 Statements](#m3-statements) ·
[M4 Large objects and bulk](#m4-large-objects-and-bulk) ·
[M5 Settings](#m5-settings) · [M6 Throughput](#m6-throughput) ·
[M7 Standard API](#m7-standard-api) · [M8 Parity audit](#m8-parity-audit)

---

## M1 Codec

- Fields: `u8`, `u32`, `u64`, `i128`, flags, strings, bytes, lists and
  keys, each read with its length checked before anything is held.
- The tail: its tags in increasing order, refused out of order or where
  a message does not take them; attributes within their bounds.
- The 27 data types and the values of each, at their edges: `i128`
  limits and scales, NaN and -0.0, DECFLOAT, each interval qualifier,
  displacements -12:59 to +14:00, nested arrays, rows, multisets and
  structured values, locators, UUIDs (tag 27, its 16 octets as bytes),
  and each XML modifier.
- JSON values, tag 25, as the binary tree of turborel's RULES.md D89:
  decoded to Python's JSON values, and parameters encoded into it.
- Every request and reply, encoded and decoded, the spec's worked
  example first.
- Compressed frames, `z`, by `zlib`, inflated within the length bound.
- Malformed frames that must fail the connection.

## M2 Connect

- TCP on port 7422, a Unix socket, and on Windows the named pipe
  `\\.\pipe\turborel`.
- TLS begun on the same port, by `ssl`; the timeouts: connect 30 s, read
  unlimited by default.
- The mechanisms `trust`, `password`, `certificate`, `scram-sha-256` and
  `scram-sha-256-plus` by `tls-server-end-point` (RULES.md D1); secrets
  refused over plain TCP (SQLSTATE 28000); the SCRAM key cache, 64
  entries.
- Hello asking for every capability but compression; Ready; Status;
  terminate (60 s); cancel by key on a connection of its own (10 s).
- `test/server/`: the live tests' server set-up, with test certificates,
  SCRAM users and TRUST_LOCAL, on `ghcr.io/turborel/turborel:nightly` in
  CI, and on port 17431 locally.
- Live tests on macOS and Windows, where the nightly image does not run:
  build `turboreld` from a pinned turborel commit there, or keep live
  tests on Linux and the codec everywhere. The owner chooses.

## M3 Statements

- Query and streamed query; prepare, execute, fetch, close and
  deallocate; numbered cursors; describe; fetch-ends.
- Failures as the driver's exceptions, the class of each by its
  SQLSTATE's class (RULES.md D7), with their diagnostics; notices (the
  last 64, or a handler) and conditions; autocommit through `ends`;
  `in_transaction`.
- Rows affected, generated values, the server's time, the commit
  position.
- Multi-statement queries, query attributes, ping, reset and
  change-user.

## M4 Large objects and bulk

- Locators; reads in chunks of 256 KiB by octets or characters; create,
  append, free and hold; a reader and a writer as Python's binary and
  text streams.
- CopyIn, CopyData, CopyEnd and abandon; CSV and tab-separated import;
  CSV and native export.

## M5 Settings

- The `turborel://` URI, `Options`, the TURBOREL_* variables, the service
  file and the password file, read as turborel-client's tests read them.
- Several hosts, `load_balance`, `target` by SERVER_READ_ONLY,
  `tls_mode`, `channel_binding` and `application_name`.

## M6 Throughput

- Pipelines with a 64 KiB window, skipping on error by savepoints.
- Pools with PoolConfig's defaults, checked by Ping and returned by
  Reset.
- The SQL-agent: CONNECT, SET CONNECTION and DISCONNECT.

## M7 Standard API

- DB-API 2.0: `connect`, `threadsafety`, the connection and cursor
  objects, type objects and constructors, and the extensions that reach
  what PEP 249 has no place for (RULES.md D2).
- `turborel.aio`, the asyncio interface beside it.
- The manual, `doc/`: Installing and the API Reference's pages of the
  DB-API and `turborel.aio`, and every chapter the earlier milestones
  filled checked again against the code, every example run.

## M8 Parity audit

- Every row of CONFORMANCE.md checked against turborel-client and the
  spec, the coverage floor held, and this file empty.
- Once turborel keeps a file of sample frames beside the spec, decode
  every frame of it at a pinned commit.
