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
from turborel._codec.failures import Diagnostics, Failure, Notice
from turborel._codec.replies import Complete, Timing
from turborel._session.capabilities import Offer
from turborel._session.state import KEPT_NOTICES
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
    "CONNECT_WITHIN",
    "DEFAULT_PIPE",
    "DEFAULT_PORT",
    "KEPT_NOTICES",
    "KEY_CACHE_ENTRIES",
    "TERMINATE_WITHIN",
    "Address",
    "Batch",
    "Canceller",
    "Certificate",
    "ChannelBinding",
    "Complete",
    "Connection",
    "Diagnostics",
    "Failure",
    "KeyCache",
    "Local",
    "Mechanism",
    "Notice",
    "Offer",
    "Outcome",
    "Password",
    "Ran",
    "Rowset",
    "Scram",
    "Sink",
    "Statement",
    "Target",
    "Tcp",
    "Timeouts",
    "Timing",
    "Tls",
    "TlsChannel",
    "Trust",
    "connect",
    "connect_local",
    "connect_tls",
    "connect_to",
    "in_the_clear",
    "presenting",
    "roots",
    "tls_channel",
    "trusting",
]
