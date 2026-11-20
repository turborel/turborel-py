"""A connection to a turborel server: a session over one stream [CLIENT Connecting]."""

from __future__ import annotations

from typing import IO, TYPE_CHECKING

from turborel._client.bulk import Bulk
from turborel._session.capabilities import Offer
from turborel._transport.stream import Stream

if TYPE_CHECKING:
    import socket

    from turborel._auth.mechanisms import Mechanism
    from turborel._transport.timeouts import Timeouts


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
        """A connection over a stream the program opened, waiting as its maker set it.

        Terminate too waits as the stream's maker set it; `open_within`
        bounds a socket by timeouts of the program's [CLIENT Timeouts].

        Over a TLS socket the program opened, bind SCRAM first:
        `mechanism.bind(tls_channel(sock))` [CLIENT Connecting].

        Raises:
            Error: As logging in fails.
        """
        connection = cls(Stream(held), None, bounded=False)
        connection._log_in(user, mechanism, offer or Offer())
        return connection

    @classmethod
    def open_within(
        cls,
        held: socket.socket,
        user: str,
        mechanism: Mechanism,
        timeouts: Timeouts,
        offer: Offer | None = None,
    ) -> Connection:
        """A connection over a socket the program opened, bounded as `timeouts` say.

        Each step of the login by their `connect`, each wait after by their
        `read`, and Terminate's by `read`, else 60 seconds; its read timeout
        then changed as a connection's is [CLIENT Timeouts].

        Raises:
            Error: As logging in fails; a connection failure if a wait runs
                out.
        """
        stream = Stream(held)
        stream.set_timeout(timeouts.connect)
        connection = cls(stream, None, bounded=True)
        connection._log_in(user, mechanism, offer or Offer())
        connection.set_read_timeout(timeouts.read)
        return connection
