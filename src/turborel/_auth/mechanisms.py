"""The mechanisms a client proves its user by [PROTOCOL Mechanisms] [CLIENT Connecting].

Each gives Hello its name and its first bytes, then answers each
Challenge until the server sends Ready, as turborel-client's
`mechanism.rs` and `scram.rs` do. `Password` and `Scram` are secret: a
connection refuses to send them over plain TCP (SQLSTATE 28000), unless
the program asks for SCRAM in the clear.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, ClassVar, Final

from turborel._auth import scram
from turborel._auth.endpoint import end_point
from turborel._errors import connection_failure

if TYPE_CHECKING:
    from turborel._auth.cache import KeyCache

TRUST: Final = "trust"
"""The mechanism `trust`: the server trusts a client of its own machine."""
PASSWORD: Final = "password"  # noqa: S105  # A mechanism's name, no secret.
"""The mechanism `password`: the password, sent whole."""
CERTIFICATE: Final = "certificate"
"""The mechanism `certificate`: the TLS client certificate's common name."""

_FINAL_PREFIXES: Final = (b"v=", b"e=")


@dataclass(frozen=True, slots=True)
class TlsChannel:
    """What a TLS connection offers SCRAM to bind.

    The server's certificate, of which `tls-server-end-point` is made,
    and `tls-exporter`'s keying material, which Python's `ssl` does not
    export (RULES.md D1).
    """

    certificate: bytes | None = field(default=None, repr=False)
    exporter: bytes | None = field(default=None, repr=False)


class ChannelBinding(Enum):
    """Whether SCRAM binds its exchange to the TLS connection carrying it."""

    DISABLE = "disable"
    """Bind nothing."""
    PREFER = "prefer"
    """Bind where the connection has a binding."""
    REQUIRE = "require"
    """Refuse an exchange not bound."""


class Mechanism:
    """A mechanism of authentication: its name, first bytes and answers."""

    NAME: ClassVar[str] = ""
    """The mechanism's name, as Hello names it."""

    @property
    def name(self) -> str:
        """The mechanism's name, as Hello names it."""
        return self.NAME

    def initial(self) -> bytes:
        """The mechanism's first bytes, sent in Hello or ChangeUser."""
        return b""

    def answer(self, challenge: bytes) -> bytes:
        """The answer to a Challenge.

        Raises:
            OperationalError: SQLSTATE 08006, of a mechanism that has no
                answer, or 28000 of one that refuses the challenge.
        """
        msg = f"{self.name} has no answer to a challenge {len(challenge)} bytes long"
        raise connection_failure(msg)

    @property
    def secret(self) -> bool:
        """Whether it gives away a secret over plain TCP."""
        return False

    def ready(self) -> None:
        """Called on Ready: check the server proved what it should.

        Raises:
            OperationalError: SQLSTATE 08006, if it did not.
        """

    def bind(self, channel: TlsChannel) -> None:
        """Called before Hello over TLS, with what the connection offers to bind."""

    def refused(self) -> None:
        """Called when the server refuses the login."""


class Trust(Mechanism):
    """`trust`: the server trusts the user as it names itself, if it is local."""

    NAME = TRUST

    def __repr__(self) -> str:
        """Its name."""
        return "Trust()"


class Certificate(Mechanism):
    """`certificate`: the user proved by the TLS client certificate presented."""

    NAME = CERTIFICATE

    def __repr__(self) -> str:
        """Its name."""
        return "Certificate()"


class Password(Mechanism):
    """`password`: the password sent whole, only over TLS or a local socket."""

    NAME = PASSWORD

    def __init__(self, password: str) -> None:
        """Prove `password`."""
        self._password = password

    def __repr__(self) -> str:
        """Never the password (R-SAFE-4)."""
        return "Password(..)"

    def initial(self) -> bytes:
        """The password's UTF-8."""
        return self._password.encode()

    @property
    def secret(self) -> bool:
        """It is: never over plain TCP."""
        return True


class Scram(Mechanism):
    """SCRAM-SHA-256, or SCRAM-SHA-256-PLUS over TLS, of a password."""

    def __init__(
        self,
        password: str,
        *,
        in_the_clear: bool = False,
        channel_binding: ChannelBinding = ChannelBinding.PREFER,
        cache: KeyCache | None = None,
    ) -> None:
        """Prove `password` by SCRAM.

        Args:
            password: The user's password, never sent.
            in_the_clear: Allow it over plain TCP, for a server whose
                SERVER.SCRAM_WITHOUT_TLS is ON.
            channel_binding: Whether to bind the TLS channel.
            cache: A key cache to keep and find derived keys in.
        """
        self._password = password
        self._clear = in_the_clear
        self._binding = channel_binding
        self._cache = cache
        self._channel = scram.Channel()
        self._exchange: scram.Client | None = None
        self._used: tuple[bytes, int] | None = None

    def __repr__(self) -> str:
        """Never the password (R-SAFE-4)."""
        return "Scram(..)"

    @property
    def name(self) -> str:
        """`scram-sha-256-plus` where it binds the channel, else `scram-sha-256`."""
        return scram.MECHANISM_PLUS if self._channel.bound else scram.MECHANISM

    @property
    def secret(self) -> bool:
        """Unless the program asked for it in the clear."""
        return not self._clear

    def bind(self, channel: TlsChannel) -> None:
        """Bind by `tls-exporter` if offered, else `tls-server-end-point`."""
        if self._binding == ChannelBinding.DISABLE:
            return
        if channel.exporter is not None:
            self._channel = scram.Channel(scram.Binding.EXPORTER, channel.exporter)
            return
        point = None if channel.certificate is None else end_point(channel.certificate)
        if point is not None:
            self._channel = scram.Channel(scram.Binding.END_POINT, point)
        else:
            self._channel = scram.Channel(scram.Binding.UNOFFERED)

    def initial(self) -> bytes:
        """client-first, of a fresh nonce; the channel bound once, then unbound."""
        channel, self._channel = self._channel, scram.Channel()
        self._exchange = scram.Client("", self._password, channel)
        self._used = None
        return self._exchange.first(scram.nonce())

    def answer(self, challenge: bytes) -> bytes:
        """client-final to server-first; nothing to server-final, once checked."""
        try:
            if challenge.startswith(_FINAL_PREFIXES):
                self._started().verify(challenge)
                return b""
            return self._prove(challenge)
        except Exception:
            self._forget()
            raise

    def _started(self) -> scram.Client:
        if self._exchange is None:
            msg = "SCRAM was not begun"
            raise connection_failure(msg)
        return self._exchange

    def _prove(self, challenge: bytes) -> bytes:
        exchange = self._started()
        if self._binding == ChannelBinding.REQUIRE and not exchange.channel.bound:
            msg = "channel binding is required, and this connection is not bound"
            raise scram.refused(msg)
        first = exchange.read(challenge)
        if self._cache is not None:
            keys = self._cache.derived(self._password, first.salt, first.iterations)
        else:
            keys = scram.Derived.of(self._password, first.salt, first.iterations)
        self._used = (first.salt, first.iterations)
        return exchange.prove(first, keys)

    def ready(self) -> None:
        """Refuse a Ready before the server proved it knows the user's verifier."""
        if self._exchange is None or not self._exchange.verified:
            msg = "the server did not prove it knows the user's verifier"
            raise connection_failure(msg)

    def refused(self) -> None:
        """Forget the keys the refused login used."""
        self._forget()

    def _forget(self) -> None:
        if self._cache is not None and self._used is not None:
            self._cache.forget(self._password, *self._used)
        self._used = None
