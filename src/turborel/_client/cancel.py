"""What cancels the statement a connection runs, from another thread.

[PROTOCOL Cancel 'Z'] [CLIENT Running statements]
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from turborel._codec import requests
from turborel._codec.frames import HEADER_BYTES
from turborel._transport.target import open_target
from turborel._transport.timeouts import CANCEL_WITHIN

if TYPE_CHECKING:
    from turborel._transport.target import Target


class Canceller:
    """What cancels the statement a connection runs, from another thread.

    The key is the session's secret, never shown (R-SAFE-4).
    """

    def __init__(self, target: Target, key: bytes) -> None:
        """Cancel by `key` at `target`."""
        self._target = target
        self._key = key

    def __repr__(self) -> str:
        """Never the key."""
        return "Canceller(..)"

    def cancel(self, within: float = CANCEL_WITHIN) -> None:
        """Cancel, on a connection of its own, giving up after `within` seconds.

        The statement cancelled fails with SQLCODE -920, SQLSTATE TB920
        [PROTOCOL Cancel 'Z'] [CLIENT Running statements].

        Raises:
            OperationalError: SQLSTATE 08006, if the server cannot be reached
                or does not close in time.
        """
        stream, _ = open_target(self._target, within)
        try:
            stream.set_timeout(within)
            stream.write(requests.Cancel(self._key).encode())
            stream.read_to_end(HEADER_BYTES)
        finally:
            stream.close()
