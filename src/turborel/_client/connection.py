"""A connection to a turborel server: a session over one stream [CLIENT Connecting]."""

from __future__ import annotations

from typing import IO, TYPE_CHECKING

from turborel._client.bulk import Bulk
from turborel._session.capabilities import Offer
from turborel._transport.stream import Stream

if TYPE_CHECKING:
    import socket

    from turborel._auth.mechanisms import Mechanism


class Connection(Bulk):
    """A session of a turborel server, over one stream."""

    @classmethod
    def open(
        cls,
        held: socket.socket | IO[bytes],
        user: str,
        mechanism: Mechanism,
        offer: Offer | None = None,
    ) -> Connection:
        """A connection over a stream the program opened, which bounds its waits.

        Over a TLS socket the program opened, bind SCRAM first:
        `mechanism.bind(tls_channel(sock))` [CLIENT Connecting].

        Raises:
            Error: As logging in fails.
        """
        connection = cls(Stream(held), None, bounded=False)
        connection._log_in(user, mechanism, offer or Offer())
        return connection
