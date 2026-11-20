"""Fixtures of the auth layer's tests: certificates' DER, built by the test.

Just enough of a certificate for `tls-server-end-point`: a SEQUENCE of a
TBSCertificate, a signature AlgorithmIdentifier and a signature, as
turborel-protocol's `scram/binding.rs` tests build them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

SEQUENCE = 0x30
OID = 0x06
ECDSA_SHA256 = bytes.fromhex("2a8648ce3d040302")


def tlv(tag: int, body: bytes) -> bytes:
    """A DER element: its tag, its length in short form, its body."""
    return bytes([tag, len(body)]) + body


def algorithm(oid: bytes, parameters: bytes = b"") -> bytes:
    """An AlgorithmIdentifier of `oid` and its `parameters`."""
    return tlv(SEQUENCE, tlv(OID, oid) + parameters)


def certificate(signature: bytes) -> bytes:
    """A certificate signed by the algorithm `signature` names."""
    return tlv(
        SEQUENCE, tlv(SEQUENCE, bytes([0x02, 1, 7])) + signature + tlv(0x03, b"\x00")
    )


@pytest.fixture
def ecdsa_certificate() -> bytes:
    """A certificate signed by ECDSA with SHA-256."""
    return certificate(algorithm(ECDSA_SHA256))


@pytest.fixture
def der() -> tuple[
    Callable[[int, bytes], bytes], Callable[..., bytes], Callable[[bytes], bytes]
]:
    """The builders: `tlv`, `algorithm` and `certificate`."""
    return tlv, algorithm, certificate
