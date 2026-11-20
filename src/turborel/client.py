"""The low-level client: a blocking connection to a turborel server.

It does all that Turborel's own client library, turborel-client, does,
beneath the DB-API (RULES.md D2), and is the driver's public interface to
what the DB-API has no place for. `connect` connects over TCP,
`connect_local` over a Unix socket or, on Windows, a named pipe,
`connect_tls` over TLS, and `connect_to` to any `Target`; each takes the
user to connect as and a mechanism that proves it [CLIENT Connecting].

    >>> conn = connect("127.0.0.1", "ANN", Trust())  # doctest: +SKIP
    >>> conn.server, conn.authorization  # doctest: +SKIP
    ('turborel 0.0.0 (alpha)', 'ANN')
"""

from __future__ import annotations

from turborel._auth.cache import KEY_CACHE_ENTRIES, KeyCache
from turborel._auth.mechanisms import (
    Certificate,
    ChannelBinding,
    Mechanism,
    Password,
    Scram,
    TlsChannel,
    Trust,
)
from turborel._client.bulk import Copying
from turborel._client.cancel import Canceller
from turborel._client.connect import (
    Address,
    connect,
    connect_local,
    connect_tls,
    connect_to,
    in_the_clear,
)
from turborel._client.connection import Connection
from turborel._client.lobs import Lob, LobReader, LobWriter
from turborel._codec.composites import Column, Declared
from turborel._codec.failures import Diagnostics, Failure, Notice
from turborel._codec.replies import Complete, Timing
from turborel._copy.copying import CHUNK_BYTES
from turborel._copy.delimited import DEFAULT_MAX_RECORD, Delimited, Dialect
from turborel._copy.exporting import ExportFormat, read_native
from turborel._copy.importing import (
    DEFAULT_BATCH,
    Import,
    Imported,
    ImportFailure,
    Rejected,
    import_rows,
)
from turborel._copy.sources import Heading, Position, Record, Source, SourceError
from turborel._lobs.locators import CHUNK_OCTETS, LOB_INLINE_OCTETS
from turborel._pipeline.pipelines import (
    PIPELINE_WINDOW,
    SKIPPED,
    OnError,
    Pipeline,
    Skipped,
)
from turborel._pool.agent import Agent, Connector
from turborel._pool.pools import (
    DEFAULT_IDLE_TIMEOUT,
    DEFAULT_MAX,
    DEFAULT_MAX_LIFETIME,
    DEFAULT_WAIT,
    Pool,
    PoolConfig,
    Pooled,
)
from turborel._pool.reset import RESET_MOST_STATEMENTS, RESET_WITHIN
from turborel._session.capabilities import Offer
from turborel._session.state import KEPT_NOTICES
from turborel._settings.failover import Role, role
from turborel._settings.options import ENVIRONMENT, KEYS, Options
from turborel._settings.settings import (
    DEFAULT_HOST,
    DEFAULT_PASSFILE,
    DEFAULT_SERVICE_FILE,
    Host,
    Settings,
    TlsFiles,
)
from turborel._settings.uri import SCHEME
from turborel._settings.values import LoadBalance, TargetRole, TlsMode
from turborel._statements.prepared import Batch, Statement
from turborel._statements.queries import Outcome, Ran, Rowset, Sink
from turborel._tls.contexts import channel as tls_channel
from turborel._tls.contexts import presenting, roots, trusting
from turborel._transport.target import (
    DEFAULT_PIPE,
    DEFAULT_PORT,
    Local,
    Target,
    Tcp,
    Tls,
)
from turborel._transport.timeouts import (
    CANCEL_WITHIN,
    CONNECT_WITHIN,
    TERMINATE_WITHIN,
    Timeouts,
)

__all__ = [
    "CANCEL_WITHIN",
    "CHUNK_BYTES",
    "CHUNK_OCTETS",
    "CONNECT_WITHIN",
    "DEFAULT_BATCH",
    "DEFAULT_HOST",
    "DEFAULT_IDLE_TIMEOUT",
    "DEFAULT_MAX",
    "DEFAULT_MAX_LIFETIME",
    "DEFAULT_MAX_RECORD",
    "DEFAULT_PASSFILE",
    "DEFAULT_PIPE",
    "DEFAULT_PORT",
    "DEFAULT_SERVICE_FILE",
    "DEFAULT_WAIT",
    "ENVIRONMENT",
    "KEPT_NOTICES",
    "KEYS",
    "KEY_CACHE_ENTRIES",
    "LOB_INLINE_OCTETS",
    "PIPELINE_WINDOW",
    "RESET_MOST_STATEMENTS",
    "RESET_WITHIN",
    "SCHEME",
    "SKIPPED",
    "TERMINATE_WITHIN",
    "Address",
    "Agent",
    "Batch",
    "Canceller",
    "Certificate",
    "ChannelBinding",
    "Column",
    "Complete",
    "Connection",
    "Connector",
    "Copying",
    "Declared",
    "Delimited",
    "Diagnostics",
    "Dialect",
    "ExportFormat",
    "Failure",
    "Heading",
    "Host",
    "Import",
    "ImportFailure",
    "Imported",
    "KeyCache",
    "LoadBalance",
    "Lob",
    "LobReader",
    "LobWriter",
    "Local",
    "Mechanism",
    "Notice",
    "Offer",
    "OnError",
    "Options",
    "Outcome",
    "Password",
    "Pipeline",
    "Pool",
    "PoolConfig",
    "Pooled",
    "Position",
    "Ran",
    "Record",
    "Rejected",
    "Role",
    "Rowset",
    "Scram",
    "Settings",
    "Sink",
    "Skipped",
    "Source",
    "SourceError",
    "Statement",
    "Target",
    "TargetRole",
    "Tcp",
    "Timeouts",
    "Timing",
    "Tls",
    "TlsChannel",
    "TlsFiles",
    "TlsMode",
    "Trust",
    "connect",
    "connect_local",
    "connect_tls",
    "connect_to",
    "import_rows",
    "in_the_clear",
    "presenting",
    "read_native",
    "role",
    "roots",
    "tls_channel",
    "trusting",
]
