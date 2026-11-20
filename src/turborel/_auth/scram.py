"""SCRAM-SHA-256's client side, as RFC 5802 and RFC 7677 lay it out.

[PROTOCOL Mechanisms]

    client-first:  <GS2 header>n=<user>,r=<client nonce>
    server-first:  r=<client nonce><server nonce>,s=<salt, base 64>,i=<iterations>
    client-final:  c=<GS2 header, then the data bound, base 64>,r=<both nonces>,
                   p=<ClientProof, base 64>
    server-final:  v=<ServerSignature, base 64>

    SaltedPassword  = PBKDF2-HMAC-SHA-256(password, salt, iterations)
    ClientKey       = HMAC(SaltedPassword, "Client Key")
    StoredKey       = SHA-256(ClientKey)
    ServerKey       = HMAC(SaltedPassword, "Server Key")
    AuthMessage     = client-first without its GS2 header, server-first,
                      client-final without its proof, by commas
    ClientProof     = ClientKey XOR HMAC(StoredKey, AuthMessage)
    ServerSignature = HMAC(ServerKey, AuthMessage)

As turborel-protocol's `scram/client.rs`: a password is its UTF-8 bytes,
without SASLprep; the channel is bound by `tls-server-end-point` or
`tls-exporter` as the GS2 header names, `n` binding none and `y` saying
the client could but sees no binding offered. Every failure is SQLSTATE
28000, as turborel-client's.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from enum import Enum
from typing import Final

from turborel._errors import CONNECTION_FAILURE_SQLCODE, OperationalError

MECHANISM: Final = "scram-sha-256"
"""The mechanism's name, unbound."""
MECHANISM_PLUS: Final = "scram-sha-256-plus"
"""The mechanism's name, bound to its TLS channel."""

KEY_BYTES: Final = 32
"""A key's bytes: SHA-256's."""
NONCE_BYTES: Final = 18
"""The random bytes of a client's nonce, before base 64: 24 characters."""

INVALID_AUTHORIZATION: Final = "28000"
"""SQLSTATE 28000, every SCRAM failure's."""

_GS2_NONE: Final = "n,,"
_GS2_UNOFFERED: Final = "y,,"
_GS2_END_POINT: Final = "p=tls-server-end-point,,"
_GS2_EXPORTER: Final = "p=tls-exporter,,"
_CLIENT_KEY: Final = b"Client Key"
_SERVER_KEY: Final = b"Server Key"
_ERROR: Final = "e="
_SIGNATURE: Final = "v"
_NONCE_FIRST: Final = 0x21
_NONCE_LAST: Final = 0x7E
_U32_MAX: Final = 0xFFFF_FFFF


def refused(why: str) -> OperationalError:
    """A SCRAM failure: SQLCODE -919, SQLSTATE 28000."""
    return OperationalError(
        f"SCRAM: {why}",
        sqlcode=CONNECTION_FAILURE_SQLCODE,
        sqlstate=INVALID_AUTHORIZATION,
    )


class Binding(Enum):
    """How a client-first's GS2 header binds the channel."""

    UNBOUND = _GS2_NONE
    UNOFFERED = _GS2_UNOFFERED
    END_POINT = _GS2_END_POINT
    EXPORTER = _GS2_EXPORTER


@dataclass(frozen=True, slots=True)
class Channel:
    """The channel an exchange binds: its kind, and the data bound."""

    binding: Binding = Binding.UNBOUND
    data: bytes = field(default=b"", repr=False)

    @property
    def bound(self) -> bool:
        """Whether it binds a TLS channel, as SCRAM-SHA-256-PLUS does."""
        return self.binding in (Binding.END_POINT, Binding.EXPORTER)

    def input(self) -> bytes:
        """The c= attribute's input: the GS2 header, then the data bound."""
        return self.binding.value.encode() + self.data


def encode64(data: bytes) -> str:
    """`data` in base 64, padded."""
    return base64.b64encode(data).decode("ascii")


def decode64(text: str) -> bytes | None:
    """The bytes of `text` in base 64, if it is base 64 exactly as written.

    As turborel's decoder: padded, no other character, no stray bits.
    """
    try:
        data = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        return None
    return data if encode64(data) == text else None


def nonce() -> str:
    """A client's nonce: 18 random bytes, in base 64."""
    return encode64(secrets.token_bytes(NONCE_BYTES))


def _hmac(key: bytes, data: bytes) -> bytes:
    return hmac.digest(key, data, "sha256")


@dataclass(frozen=True, slots=True)
class Derived:
    """The keys a password derives: ClientKey and ServerKey."""

    client: bytes = field(repr=False)
    server: bytes = field(repr=False)

    @classmethod
    def of(cls, password: str, salt: bytes, iterations: int) -> Derived:
        """The keys `password` derives under `salt` and `iterations`."""
        salted = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), salt, iterations, KEY_BYTES
        )
        return cls(_hmac(salted, _CLIENT_KEY), _hmac(salted, _SERVER_KEY))


@dataclass(frozen=True, slots=True)
class ServerFirst:
    """The server's first message, read."""

    message: str
    both: str
    """Both nonces, the client's first."""
    salt: bytes
    iterations: int


def _attribute(text: str | None, name: str) -> str:
    if text is None:
        msg = f"the attribute {name} is missing"
        raise refused(msg)
    if not text.startswith(name + "="):
        msg = f"the attribute {name} was expected, not {text}"
        raise refused(msg)
    return text[len(name) + 1 :]


def _is_nonce(text: str) -> bool:
    return bool(text) and all(
        _NONCE_FIRST <= ord(c) <= _NONCE_LAST and c != "," for c in text
    )


def _saslname(user: str) -> str:
    return user.replace("=", "=3D").replace(",", "=2C")


def _text(message: bytes) -> str:
    try:
        return message.decode("utf-8")
    except UnicodeDecodeError as e:
        msg = "a message is not UTF-8"
        raise refused(msg) from e


class Client:
    """One SCRAM exchange's client side, step by step."""

    def __init__(
        self, user: str, password: str, channel: Channel | None = None
    ) -> None:
        """Begin an exchange as `user`, proving `password`, binding `channel`."""
        self._user = user
        self._password = password
        self.channel = channel or Channel()
        self._bare = ""
        self._nonce = ""
        self._expected: bytes | None = None
        self.verified = False

    def first(self, client_nonce: str) -> bytes:
        """client-first, of the nonce `client_nonce`."""
        self._nonce = client_nonce
        self._bare = f"n={_saslname(self._user)},r={client_nonce}"
        return (self.channel.binding.value + self._bare).encode()

    def read(self, server_first: bytes) -> ServerFirst:
        """server-first, read and checked.

        Raises:
            OperationalError: SQLSTATE 28000, out of turn, malformed, or of a
                nonce that does not extend the client's.
        """
        if not self._nonce:
            msg = "the server's first message came out of turn"
            raise refused(msg)
        message = _text(server_first)
        fields = message.split(",")
        both = _attribute(fields[0], "r")
        salt = _attribute(fields[1] if len(fields) > 1 else None, "s")
        iterations = _attribute(fields[2] if len(fields) > 2 else None, "i")  # noqa: PLR2004  # Its third.
        if len(fields) > 3:  # noqa: PLR2004  # r, s and i alone.
            msg = "the server's first message has more than it should"
            raise refused(msg)
        extends = len(both) > len(self._nonce) and both.startswith(self._nonce)
        if not _is_nonce(both) or not extends:
            msg = "the server's nonce does not extend the client's"
            raise refused(msg)
        raw_salt = decode64(salt)
        if raw_salt is None:
            msg = "the salt is not base 64"
            raise refused(msg)
        if not iterations.isdigit() or not 0 < int(iterations) <= _U32_MAX:
            msg = "the iterations are no positive number"
            raise refused(msg)
        return ServerFirst(message, both, raw_salt, int(iterations))

    def prove(self, first: ServerFirst, keys: Derived) -> bytes:
        """client-final, proving the password by `keys`."""
        without_proof = f"c={encode64(self.channel.input())},r={first.both}"
        auth = f"{self._bare},{first.message},{without_proof}".encode()
        stored = hashlib.sha256(keys.client).digest()
        signature = _hmac(stored, auth)
        proof = bytes(a ^ b for a, b in zip(keys.client, signature, strict=True))
        self._expected = _hmac(keys.server, auth)
        return f"{without_proof},p={encode64(proof)}".encode()

    def verify(self, server_final: bytes) -> None:
        """server-final, its signature checked.

        Raises:
            OperationalError: SQLSTATE 28000, out of turn, an error the
                server sent, or a signature that is not the server's.
        """
        if self._expected is None:
            msg = "the server's final message came out of turn"
            raise refused(msg)
        message = _text(server_final)
        if message.startswith(_ERROR):
            msg = f"the server refused: {message[len(_ERROR) :]}"
            raise refused(msg)
        signature = decode64(_attribute(message, _SIGNATURE))
        if signature is None:
            msg = "the server's signature is not base 64"
            raise refused(msg)
        if not hmac.compare_digest(signature, self._expected):
            msg = "the server did not prove it knows the user"
            raise refused(msg)
        self.verified = True
