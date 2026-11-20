"""How long a connection waits on its server [CLIENT Timeouts].

The connect timeout bounds connecting, beginning TLS, and each step of
the login: 30 seconds by default. The read timeout bounds each read or
write after: none by default, as a statement may run as long as it
must. A wait that runs out loses the connection (SQLSTATE 08006),
saying the server did not answer in time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from turborel._errors import OperationalError, connection_failure

CONNECT_WITHIN: Final = 30.0
"""The connect timeout unless the program says another, in seconds."""

TERMINATE_WITHIN: Final = 60.0
"""How long terminate waits for the server to close, with no read timeout."""

CANCEL_WITHIN: Final = 10.0
"""How long a cancel waits for its server, unless the program says another."""


@dataclass(frozen=True, slots=True)
class Timeouts:
    """How long a connection waits, in seconds; None for no limit."""

    connect: float | None = CONNECT_WITHIN
    """For connecting, TLS, and each step of the login."""
    read: float | None = None
    """For each read or write after the login."""


def io_failed(what: str, e: OSError) -> OperationalError:
    """The connection failure of an I/O error, saying a timeout as one."""
    if isinstance(e, TimeoutError):
        return connection_failure(
            f"cannot {what}: the server did not answer in time ({e})"
        )
    return connection_failure(f"cannot {what}: {e}")
