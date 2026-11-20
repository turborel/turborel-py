"""The `tls-server-end-point` channel binding of a certificate (RFC 5929 §4.1).

The data bound is the hash of the server's certificate, by the hash its
signature algorithm uses, SHA-256 where that is MD5 or SHA-1. As
turborel-protocol's `scram/binding.rs`, the certificate's DER is read
just far enough to find the algorithm: RSA and ECDSA with SHA-1 to
SHA-512, and RSASSA-PSS of one hash for both its digest and its mask. A
certificate of another algorithm, as Ed25519's, or of two hashes,
defines none.
"""

from __future__ import annotations

import hashlib
from typing import Final

SEQUENCE: Final = 0x30
"""DER's tag of a SEQUENCE."""
OID: Final = 0x06
"""DER's tag of an OBJECT IDENTIFIER."""

_LONG_FORM: Final = 0x80
_LENGTH_BITS: Final = 0x7F
_MOST_LENGTH_BYTES: Final = 4
_PSS_HASH: Final = 0xA0
_PSS_MASK: Final = 0xA1

_RSA_PSS: Final = bytes.fromhex("2a864886f70d01010a")
_MGF1: Final = bytes.fromhex("2a864886f70d010108")
_SHA1: Final = bytes.fromhex("2b0e03021a")

# Each signature algorithm, and the hash its binding uses.
_SIGNATURES: Final = {
    bytes.fromhex("2a864886f70d010104"): "sha256",  # MD5 with RSA
    bytes.fromhex("2a864886f70d010105"): "sha256",  # SHA-1 with RSA
    bytes.fromhex("2a864886f70d01010b"): "sha256",  # SHA-256 with RSA
    bytes.fromhex("2a864886f70d01010c"): "sha384",  # SHA-384 with RSA
    bytes.fromhex("2a864886f70d01010d"): "sha512",  # SHA-512 with RSA
    bytes.fromhex("2a8648ce3d0401"): "sha256",  # ECDSA with SHA-1
    bytes.fromhex("2a8648ce3d040302"): "sha256",  # ECDSA with SHA-256
    bytes.fromhex("2a8648ce3d040303"): "sha384",  # ECDSA with SHA-384
    bytes.fromhex("2a8648ce3d040304"): "sha512",  # ECDSA with SHA-512
}

# Each hash RSASSA-PSS may name, and the hash its binding uses.
_HASHES: Final = {
    _SHA1: "sha256",
    bytes.fromhex("608648016503040201"): "sha256",
    bytes.fromhex("608648016503040202"): "sha384",
    bytes.fromhex("608648016503040203"): "sha512",
}


def element(der: bytes) -> tuple[int, bytes, bytes] | None:
    """The first element of `der`: its tag, its body and what follows it."""
    if len(der) < 2:  # noqa: PLR2004  # A tag and a length.
        return None
    tag, first, rest = der[0], der[1], der[2:]
    if first < _LONG_FORM:
        length = first
    else:
        count = first & _LENGTH_BITS
        if count == 0 or count > _MOST_LENGTH_BYTES or len(rest) < count:
            return None
        length, rest = int.from_bytes(rest[:count], "big"), rest[count:]
    if len(rest) < length:
        return None
    return tag, rest[:length], rest[length:]


def expect(der: bytes, tag: int) -> tuple[bytes, bytes] | None:
    """The body of the first element of `der`, if its tag is `tag`, and the rest."""
    found = element(der)
    if found is None or found[0] != tag:
        return None
    return found[1], found[2]


def _identifier(der: bytes) -> tuple[bytes, bytes] | None:
    """An AlgorithmIdentifier's OID, and its parameters."""
    sequence = expect(der, SEQUENCE)
    return None if sequence is None else expect(sequence[0], OID)


def _pss(parameters: bytes) -> str | None:
    """The binding's hash of RSASSA-PSS of `parameters`: one hash for both."""
    sequence = expect(parameters, SEQUENCE)
    if sequence is None:
        return None
    fields, digest, mask = sequence[0], _SHA1, _SHA1
    explicit = expect(fields, _PSS_HASH)
    if explicit is not None:
        named = _identifier(explicit[0])
        if named is None:
            return None
        digest, fields = named[0], explicit[1]
    explicit = expect(fields, _PSS_MASK)
    if explicit is not None:
        function = _identifier(explicit[0])
        of = (
            None
            if function is None or function[0] != _MGF1
            else _identifier(function[1])
        )
        if of is None:
            return None
        mask = of[0]
    return _HASHES.get(digest) if digest == mask else None


def end_point(certificate: bytes) -> bytes | None:
    """The `tls-server-end-point` data of a certificate's DER; None if it has none."""
    outer = expect(certificate, SEQUENCE)
    inner = None if outer is None else expect(outer[0], SEQUENCE)
    named = None if inner is None else _identifier(inner[1])
    if named is None:
        return None
    algorithm, parameters = named
    hash_name = (
        _pss(parameters) if algorithm == _RSA_PSS else _SIGNATURES.get(algorithm)
    )
    return None if hash_name is None else hashlib.new(hash_name, certificate).digest()
