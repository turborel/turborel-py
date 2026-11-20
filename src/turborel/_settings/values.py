"""The settings that are one of a few words [CLIENT Where settings come from].

How TLS is used, whether SCRAM binds its channel, what a server must be
to be taken, and whether servers are tried in order; each written in
lower case, as a setting, the environment and a URI give it.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING, TypeVar

from turborel._auth.mechanisms import ChannelBinding
from turborel._settings.options import invalid

if TYPE_CHECKING:
    from collections.abc import Sequence


class TlsMode(Enum):
    """How a connection over TCP uses TLS; one over a local socket uses none."""

    DISABLE = "disable"
    """Never: plain TCP."""
    PREFER = "prefer"
    """TLS if the server takes it, else plain TCP; its certificate not checked."""
    REQUIRE = "require"
    """TLS or no connection; the server's certificate not checked."""
    VERIFY_CA = "verify-ca"
    """TLS, the certificate signed by an authority trusted, its name not checked."""
    VERIFY_FULL = "verify-full"
    """TLS, the certificate signed by an authority trusted and of the server's name."""

    def verifies(self) -> bool:
        """Whether the server's certificate is checked against authorities trusted."""
        return self in (TlsMode.VERIFY_CA, TlsMode.VERIFY_FULL)


class TargetRole(Enum):
    """What a server must be for a connection to it to be kept."""

    ANY = "any"
    READ_WRITE = "read-write"
    """One that takes changes: a server alone, or its group's primary."""
    READ_ONLY = "read-only"
    """One that takes none: a replica following its group's log."""


class LoadBalance(Enum):
    """Whether servers are tried in the order given."""

    DISABLE = "disable"
    RANDOM = "random"
    """In an order drawn at random for each connection."""


_BINDINGS = (
    ("disable", ChannelBinding.DISABLE),
    ("prefer", ChannelBinding.PREFER),
    ("require", ChannelBinding.REQUIRE),
)
_BOOLEANS = (("true", True), ("false", False))

_T = TypeVar("_T")


def word(key: str, text: str, words: Sequence[tuple[str, _T]]) -> _T:
    """The value of `key` the word `text` is, among `words`.

    Raises:
        OperationalError: SQLSTATE 08001, if it is none of them.
    """
    for written, value in words:
        if written == text:
            return value
    known = ", ".join(w for w, _ in words)
    msg = f"{key} is {text}, not one of {known}"
    raise invalid(msg)


def tls_mode(key: str, text: str) -> TlsMode:
    """The TLS mode `text` names, the value of `key`."""
    return word(key, text, [(m.value, m) for m in TlsMode])


def channel_binding(key: str, text: str) -> ChannelBinding:
    """The channel binding `text` names, the value of `key`."""
    return word(key, text, _BINDINGS)


def target_role(key: str, text: str) -> TargetRole:
    """The role `text` names, the value of `key`."""
    return word(key, text, [(r.value, r) for r in TargetRole])


def load_balance(key: str, text: str) -> LoadBalance:
    """The choice `text` names, the value of `key`."""
    return word(key, text, [(b.value, b) for b in LoadBalance])


def boolean(key: str, text: str) -> bool:
    """The yes or no `text` is, `true` or `false`, the value of `key`."""
    return word(key, text, _BOOLEANS)
