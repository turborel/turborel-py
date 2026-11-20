"""Tests of SCRAM-SHA-256: RFC 7677's test vector, and a server of the test's own."""

from __future__ import annotations

import hashlib
import hmac

import pytest

from turborel import OperationalError
from turborel._auth import scram
from turborel._auth.cache import KEY_CACHE_ENTRIES, KeyCache
from turborel._auth.mechanisms import ChannelBinding, Scram, TlsChannel

# RFC 7677 §3's exchange, of the user "user" and the password "pencil".
CLIENT_NONCE = "rOprNGfwEbeRWgbNEkqO"
SERVER_FIRST = (
    b"r=rOprNGfwEbeRWgbNEkqO%hvYDpWUa2RaTCAfuxFIlj)hNlF$k0,"
    b"s=W22ZaJ0SNY7soEsUEjb6gQ==,i=4096"
)
CLIENT_FINAL = (
    b"c=biws,r=rOprNGfwEbeRWgbNEkqO%hvYDpWUa2RaTCAfuxFIlj)hNlF$k0,"
    b"p=dHzbZapWIk4jUhN+Ute9ytag9zjfMHgsqmmiz7AndVQ="
)
SERVER_FINAL = b"v=6rriTRBi23WpRR/wtup+mMhUZUn/dB5nLTJRsjl95G4="


def test_rfc_7677_s_exchange() -> None:
    """Verifies: [PROTOCOL Mechanisms] [RFC 7677 §3] SCRAM-SHA-256's test vector.

    client-first, server-first, client-final with its proof, and the
    server's signature checked.
    """
    client = scram.Client("user", "pencil")
    assert client.first(CLIENT_NONCE) == b"n,,n=user,r=rOprNGfwEbeRWgbNEkqO"
    first = client.read(SERVER_FIRST)
    assert (first.iterations, len(first.salt)) == (4096, 16)
    assert (
        client.prove(first, scram.Derived.of("pencil", first.salt, first.iterations))
        == CLIENT_FINAL
    )
    client.verify(SERVER_FINAL)
    assert client.verified


@pytest.mark.parametrize(
    "server_first",
    [
        b"r=other%hvY,s=W22ZaJ0SNY7soEsUEjb6gQ==,i=4096",  # not the client's nonce
        b"r=rOprNGfwEbeRWgbNEkqO,s=W22ZaJ0SNY7soEsUEjb6gQ==,i=4096",  # not extended
        b"r=rOprNGfwEbeRWgbNEkqOx,s=W22Z*J0S,i=4096",  # a salt not base 64
        b"r=rOprNGfwEbeRWgbNEkqOx,s=W22ZaJ0SNY7soEsUEjb6gQ==,i=0",  # no iterations
        b"r=rOprNGfwEbeRWgbNEkqOx,s=W22ZaJ0SNY7soEsUEjb6gQ==",  # i missing
        b"r=rOprNGfwEbeRWgbNEkqOx,s=W22ZaJ0SNY7soEsUEjb6gQ==,i=1,m=x",  # more
        b"x=rOprNGfwEbeRWgbNEkqOx",  # not r
        b"\xff",  # not UTF-8
    ],
)
def test_a_server_first_message_not_of_rfc_5802_is_refused(server_first: bytes) -> None:
    """Verifies: [PROTOCOL Mechanisms] server-first: both nonces, salt, iterations.

    Anything else is refused with SQLSTATE 28000.
    """
    client = scram.Client("user", "pencil")
    client.first(CLIENT_NONCE)
    with pytest.raises(OperationalError) as failure:
        client.read(server_first)
    assert failure.value.sqlstate == "28000"


def test_a_signature_not_the_server_s_is_refused() -> None:
    """Verifies: [PROTOCOL Mechanisms] the server's signature checked.

    A signature of another key, an error the server sends, or a message
    out of turn is refused with SQLSTATE 28000.
    """
    out_of_turn = scram.Client("user", "pencil")
    for message in (SERVER_FIRST, SERVER_FINAL):
        with pytest.raises(OperationalError):
            (out_of_turn.read if message is SERVER_FIRST else out_of_turn.verify)(
                message
            )
    client = scram.Client("user", "pencil")
    client.first(CLIENT_NONCE)
    client.prove(client.read(SERVER_FIRST), scram.Derived.of("pencil", b"x", 1))
    for wrong in (SERVER_FINAL, b"e=invalid-proof", b"v=####"):
        with pytest.raises(OperationalError) as failure:
            client.verify(wrong)
        assert failure.value.sqlstate == "28000"
    assert not client.verified


def test_base_64_is_read_exactly_as_written() -> None:
    """Verifies: [PROTOCOL Mechanisms] [RFC 5802 §7] base 64, padded, no stray bits."""
    assert scram.decode64("cGVuY2ls") == b"pencil"
    assert scram.decode64("YQ==") == b"a"
    for text in ("YQ=", "YR==", "Y Q==", "YQ==YQ=="):
        assert scram.decode64(text) is None
    assert len(scram.nonce()) == 24


class Server:
    """A SCRAM server of the test's own: StoredKey and ServerKey of a password."""

    def __init__(
        self, password: str, salt: bytes = b"salt", iterations: int = 2
    ) -> None:
        """Know `password`'s keys under `salt` and `iterations`."""
        salted = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations, 32)
        client_key = hmac.digest(salted, b"Client Key", "sha256")
        self.stored = hashlib.sha256(client_key).digest()
        self.server_key = hmac.digest(salted, b"Server Key", "sha256")
        self.salt, self.iterations = salt, iterations
        self.bare = self.first_message = ""
        self.bound = b""

    def first(self, client_first: bytes) -> bytes:
        """server-first, to `client_first`."""
        text = client_first.decode()
        header, self.bare = text[: text.index("n=")], text[text.index("n=") :]
        nonce = self.bare.split("r=")[1] + "server"
        self.bound = header.encode()
        salt = scram.encode64(self.salt)
        self.first_message = f"r={nonce},s={salt},i={self.iterations}"
        return self.first_message.encode()

    def final(self, client_final: bytes) -> bytes:
        """server-final, if the proof is right; else e=invalid-proof."""
        text = client_final.decode()
        without, proof = text.rsplit(",p=", 1)
        auth = f"{self.bare},{self.first_message},{without}".encode()
        signature = hmac.digest(self.stored, auth, "sha256")
        given = scram.decode64(proof) or b""
        client_key = bytes(a ^ b for a, b in zip(given, signature, strict=False))
        if hashlib.sha256(client_key).digest() != self.stored:
            return b"e=invalid-proof"
        return (
            b"v="
            + scram.encode64(hmac.digest(self.server_key, auth, "sha256")).encode()
        )


def login(mechanism: Scram, server: Server) -> None:
    """A whole exchange of `mechanism` with `server`, as a connection runs it."""
    first = server.first(mechanism.initial())
    final = server.final(mechanism.answer(first))
    try:
        assert mechanism.answer(final) == b""
    except OperationalError:
        mechanism.refused()
        raise
    mechanism.ready()


def test_a_scram_login_proves_both_sides() -> None:
    """Verifies: [CLIENT Connecting] SCRAM refused unless the server proves it.

    The mechanism is secret, so never over plain TCP unless asked for in
    the clear; Ready before the server's signature is refused; its
    display form never shows the password (R-SAFE-4).
    """
    mechanism = Scram("ann's")
    assert mechanism.name == "scram-sha-256"
    assert mechanism.secret
    assert not Scram("x", in_the_clear=True).secret
    login(mechanism, Server("ann's"))
    with pytest.raises(OperationalError) as failure:
        login(Scram("wrong"), Server("ann's"))
    assert failure.value.sqlstate == "28000"
    early = Scram("ann's")
    early.initial()
    with pytest.raises(OperationalError) as early_failure:
        early.ready()
    assert early_failure.value.sqlstate == "08006"
    assert "ann" not in repr(mechanism)


def test_the_key_cache_hits_the_same_salt_and_password_alone() -> None:
    """Verifies: [CLIENT The SCRAM key cache] keys kept, found by salt, iterations, tag.

    A later login of the same salt and iterations hits; another salt
    misses; a wrong password finds nothing and its keys are forgotten as
    the login fails; the cache shows neither password nor keys.
    """
    cache = KeyCache()
    login(Scram("right", cache=cache), Server("right"))
    assert (cache.lookups(), len(cache)) == ((0, 1), 1)
    login(Scram("right", cache=cache), Server("right"))
    assert cache.lookups() == (1, 1)
    login(Scram("right", cache=cache), Server("right", salt=b"other"))
    assert (cache.lookups(), len(cache)) == ((1, 2), 2)
    with pytest.raises(OperationalError):
        login(Scram("wrong", cache=cache), Server("right"))
    assert (cache.lookups(), len(cache)) == ((1, 3), 2)
    assert "right" not in repr(cache)
    cache.clear()
    assert len(cache) == 0


def test_a_failed_login_forgets_its_keys_and_the_cache_is_bounded() -> None:
    """Verifies: [CLIENT The SCRAM key cache] dropped as a login fails; 64 at most.

    The oldest entry is dropped first, so its salt misses again.
    """
    cache = KeyCache()
    login(Scram("old", cache=cache), Server("old"))
    with pytest.raises(OperationalError):
        login(Scram("old", cache=cache), Server("new"))
    assert (cache.lookups(), len(cache)) == ((1, 1), 0)
    for n in range(KEY_CACHE_ENTRIES + 1):
        login(Scram("p", cache=cache), Server("p", salt=bytes([n]), iterations=1))
    assert len(cache) == KEY_CACHE_ENTRIES
    hits = cache.lookups()[0]
    login(Scram("p", cache=cache), Server("p", salt=bytes([0]), iterations=1))
    assert cache.lookups()[0] == hits


def test_channel_binding_is_disabled_preferred_or_required(
    ecdsa_certificate: bytes,
) -> None:
    """Verifies: [PROTOCOL Mechanisms] SCRAM-SHA-256-PLUS bound by tls-server-end-point.

    [CLIENT TLS by mode] bound where the connection offers a binding;
    `y` where it offers none; nothing bound when disabled; refused when
    required and not bound. The certificate's hash, as its signature's
    hash says, is the data bound.
    """
    unbound = Scram("p", channel_binding=ChannelBinding.REQUIRE)
    unbound.initial()
    with pytest.raises(OperationalError) as failure:
        unbound.answer(b"r=x,s=c2FsdA==,i=1")
    assert failure.value.sqlstate == "28000"
    preferred = Scram("p")
    preferred.bind(TlsChannel(certificate=ecdsa_certificate))
    assert preferred.name == "scram-sha-256-plus"
    assert preferred.initial().startswith(b"p=tls-server-end-point,,")
    disabled = Scram("p", channel_binding=ChannelBinding.DISABLE)
    disabled.bind(TlsChannel(certificate=ecdsa_certificate))
    assert disabled.initial().startswith(b"n,,")
    unoffered = Scram("p")
    unoffered.bind(TlsChannel(certificate=b"\x30\x00"))
    assert unoffered.initial().startswith(b"y,,")
    exported = Scram("p")
    exported.bind(TlsChannel(exporter=bytes(32)))
    assert exported.initial().startswith(b"p=tls-exporter,,")
