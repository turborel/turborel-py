"""Tests of `tls-server-end-point`: the hash a certificate's signature names."""

from __future__ import annotations

import hashlib
from collections.abc import Callable

import pytest

from turborel._auth.endpoint import element, end_point, expect

Builders = tuple[
    Callable[[int, bytes], bytes], Callable[..., bytes], Callable[[bytes], bytes]
]

MD5_RSA = bytes.fromhex("2a864886f70d010104")
SHA1_RSA = bytes.fromhex("2a864886f70d010105")
SHA256_RSA = bytes.fromhex("2a864886f70d01010b")
SHA384_RSA = bytes.fromhex("2a864886f70d01010c")
SHA512_RSA = bytes.fromhex("2a864886f70d01010d")
SHA1_ECDSA = bytes.fromhex("2a8648ce3d0401")
SHA256_ECDSA = bytes.fromhex("2a8648ce3d040302")
SHA384_ECDSA = bytes.fromhex("2a8648ce3d040303")
SHA512_ECDSA = bytes.fromhex("2a8648ce3d040304")
RSA_PSS = bytes.fromhex("2a864886f70d01010a")
MGF1 = bytes.fromhex("2a864886f70d010108")
SHA1 = bytes.fromhex("2b0e03021a")
SHA256 = bytes.fromhex("608648016503040201")
SHA384 = bytes.fromhex("608648016503040202")
SHA512 = bytes.fromhex("608648016503040203")
NULL = bytes([0x05, 0])


@pytest.mark.parametrize(
    ("oid", "hash_name"),
    [
        (MD5_RSA, "sha256"),
        (SHA1_RSA, "sha256"),
        (SHA1_ECDSA, "sha256"),
        (SHA256_RSA, "sha256"),
        (SHA256_ECDSA, "sha256"),
        (SHA384_RSA, "sha384"),
        (SHA384_ECDSA, "sha384"),
        (SHA512_RSA, "sha512"),
        (SHA512_ECDSA, "sha512"),
    ],
)
def test_the_signature_s_hash_chooses_the_binding_s(
    der: Builders, oid: bytes, hash_name: str
) -> None:
    """Verifies: [PROTOCOL Mechanisms] [RFC 5929 §4.1] tls-server-end-point's hash.

    The certificate's signature hash, SHA-256 in place of MD5 and SHA-1.
    """
    _, algorithm, certificate = der
    cert = certificate(algorithm(oid, NULL))
    assert end_point(cert) == hashlib.new(hash_name, cert).digest()


def pss(der: Builders, hash_oid: bytes | None, mask: bytes | None) -> bytes:
    """An RSASSA-PSS AlgorithmIdentifier of a hash and a mask's, either left out."""
    tlv, algorithm, _ = der
    hashed = b"" if hash_oid is None else tlv(0xA0, algorithm(hash_oid, NULL))
    masked = b"" if mask is None else tlv(0xA1, algorithm(MGF1, algorithm(mask, NULL)))
    return algorithm(RSA_PSS, tlv(0x30, hashed + masked))


def test_rsassa_pss_is_bound_by_its_one_hash(der: Builders) -> None:
    """Verifies: [PROTOCOL Mechanisms] [RFC 5929 §4.1] RSASSA-PSS of one hash.

    SHA-1 by default, so SHA-256's binding; of two hashes, or a mask not
    MGF1, or no parameters, none.
    """
    tlv, algorithm, certificate = der
    same = certificate(pss(der, SHA384, SHA384))
    assert end_point(same) == hashlib.sha384(same).digest()
    defaults = certificate(pss(der, None, None))
    assert end_point(defaults) == hashlib.sha256(defaults).digest()
    assert end_point(certificate(pss(der, SHA256, None))) is None
    assert end_point(certificate(pss(der, SHA512, SHA256))) is None
    other = tlv(0xA1, algorithm(SHA1_RSA, algorithm(SHA256)))
    masked = algorithm(RSA_PSS, tlv(0x30, tlv(0xA0, algorithm(SHA256)) + other))
    assert end_point(certificate(masked)) is None
    assert end_point(certificate(pss(der, MGF1, MGF1))) is None
    assert end_point(certificate(algorithm(RSA_PSS))) is None


def test_no_binding_without_one_known_hash(der: Builders) -> None:
    """Verifies: [PROTOCOL Mechanisms] Ed25519 defines none, nor a cut certificate."""
    tlv, algorithm, certificate = der
    assert end_point(certificate(algorithm(bytes([0x2B, 0x65, 0x70])))) is None
    whole = certificate(algorithm(SHA256_ECDSA))
    for cut in range(len(whole)):
        assert end_point(whole[:cut]) is None
    assert end_point(certificate(tlv(0x30, NULL))) is None


def test_der_elements_are_read_by_tag_and_length() -> None:
    """Verifies: [DESIGN] D13 DER read as turborel-protocol's `der.rs` reads it."""
    assert element(bytes([0x06, 1, 7, 9])) == (0x06, b"\x07", b"\x09")
    long = bytes([0x30, 0x81, 2, 1, 2, 3])
    assert expect(long, 0x30) == (b"\x01\x02", b"\x03")
    assert expect(long, 0x06) is None
    for short in (
        b"",
        b"\x30",
        b"\x30\x02\x01",
        b"\x30\x80",
        b"\x30\x85\x00\x00\x00\x00\x01",
        b"\x30\x82\x01",
    ):
        assert element(short) is None
