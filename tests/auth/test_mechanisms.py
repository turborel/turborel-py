"""Tests of the mechanisms but SCRAM: trust, password and certificate."""

from __future__ import annotations

import pytest

from turborel import OperationalError
from turborel._auth.mechanisms import Certificate, Password, Scram, TlsChannel, Trust


@pytest.mark.parametrize(
    ("mechanism", "name", "initial", "secret"),
    [
        (Trust(), "trust", b"", False),
        (Certificate(), "certificate", b"", False),
        (Password("ann's"), "password", b"ann's", True),
    ],
)
def test_a_mechanism_is_its_name_and_first_bytes(
    mechanism: Trust | Certificate | Password,
    name: str,
    initial: bytes,
    *,
    secret: bool,
) -> None:
    """Verifies: [PROTOCOL Mechanisms] trust, password and certificate.

    `password`'s first bytes are the password's UTF-8, and it is secret,
    sent only over TLS or a local socket; none answers a Challenge.
    """
    assert (mechanism.name, mechanism.initial(), mechanism.secret) == (
        name,
        initial,
        secret,
    )
    mechanism.bind(TlsChannel())
    mechanism.ready()
    mechanism.refused()
    with pytest.raises(OperationalError) as failure:
        mechanism.answer(b"challenge")
    assert failure.value.sqlstate == "08006"
    assert "ann" not in repr(mechanism)


def test_scram_answers_nothing_before_it_begins() -> None:
    """Verifies: [PROTOCOL Mechanisms] SCRAM's exchange begins with client-first."""
    with pytest.raises(OperationalError) as failure:
        Scram("p").answer(b"r=x,s=c2FsdA==,i=1")
    assert failure.value.sqlstate == "08006"
