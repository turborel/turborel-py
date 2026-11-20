"""TLS configurations, and a TCP connection secured [CLIENT Connecting].

As turborel-client's `tls.rs`: a client's TLS trusts the authorities of
the files it is given alone, unless the platform's are asked for; it
offers TLS 1.2 and 1.3, and checks the server's certificate and name. A
client presenting a certificate, to log in by `certificate`, names a PEM
file of its chain and one of its key. The platform's authorities are
those `ssl` loads by default: the platform's store, or the files
SSL_CERT_FILE and SSL_CERT_DIR name, where either is set.
"""

from __future__ import annotations

import ssl
from dataclasses import dataclass
from typing import TYPE_CHECKING

from turborel._auth.mechanisms import TlsChannel
from turborel._errors import OperationalError, connection_failure

if TYPE_CHECKING:
    import socket


def _unreadable(path: str, e: OSError | ssl.SSLError) -> OperationalError:
    return connection_failure(f"cannot read {path}: {e}")


def _context() -> ssl.SSLContext:
    """A client context of TLS 1.2 and later, checking certificates and names."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def _trust_file(context: ssl.SSLContext, path: str) -> None:
    before = context.cert_store_stats()["x509_ca"]
    try:
        context.load_verify_locations(cafile=path)
    except (OSError, ssl.SSLError) as e:
        raise _unreadable(path, e) from e
    if context.cert_store_stats()["x509_ca"] == before:
        msg = f"{path} holds no certificate"
        raise connection_failure(msg)


def roots(file: str | None = None, *, platform: bool = False) -> ssl.SSLContext:
    """A context trusting the authorities of `file`, the platform's, or both.

    Raises:
        OperationalError: SQLSTATE 08006, if the file cannot be read or
            holds no certificate, or nothing is trusted at all.
    """
    if file is None and not platform:
        msg = "no certificate authority is trusted: name a file, or the platform's"
        raise connection_failure(msg)
    context = _context()
    if file is not None:
        _trust_file(context, file)
    if platform:
        context.load_default_certs(ssl.Purpose.SERVER_AUTH)
    return context


def trusting(file: str) -> ssl.SSLContext:
    """A context trusting the authorities of the PEM file `file` alone."""
    return roots(file)


def presenting(file: str, chain: str, key: str) -> ssl.SSLContext:
    """A context trusting `file`'s authorities and presenting a certificate.

    Args:
        file: The PEM file of the authorities trusted.
        chain: The PEM file of the client's certificate chain.
        key: The PEM file of its private key.

    Raises:
        OperationalError: SQLSTATE 08006, if a file cannot be read.
    """
    context = trusting(file)
    present(context, chain, key)
    return context


def present(context: ssl.SSLContext, chain: str, key: str) -> None:
    """Make `context` present the certificate chain `chain` and its key `key`."""
    try:
        context.load_cert_chain(chain, key)
    except (OSError, ssl.SSLError) as e:
        raise connection_failure(f"cannot present {chain}: {e}") from e


@dataclass(frozen=True, slots=True)
class Secured:
    """A TCP connection secured, and what its TLS offers SCRAM to bind."""

    socket: ssl.SSLSocket
    channel: TlsChannel


def secure(tcp: socket.socket, server_name: str, context: ssl.SSLContext) -> Secured:
    """TLS begun on `tcp`, its handshake done, the server's certificate kept.

    The server tells TLS from the protocol by the first byte, 22, so TLS
    begins on the same port [PROTOCOL The Native Protocol].

    Raises:
        OperationalError: SQLSTATE 08006, if the handshake fails.
    """
    try:
        secured = context.wrap_socket(tcp, server_hostname=server_name)
    except (OSError, ssl.SSLError, ValueError) as e:
        tcp.close()
        raise connection_failure(f"the TLS handshake failed: {e}") from e
    return Secured(secured, channel(secured))


def channel(secured: ssl.SSLSocket) -> TlsChannel:
    """What the TLS connection `secured` offers SCRAM to bind.

    The server's certificate, of which `tls-server-end-point` is made;
    `ssl` exports no keying material, so no `tls-exporter` (RULES.md D1).
    """
    return TlsChannel(certificate=secured.getpeercert(binary_form=True))
