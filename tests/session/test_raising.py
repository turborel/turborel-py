"""Tests of a failure the server sent, raised by its SQLSTATE's class."""

from __future__ import annotations

import pytest

from turborel import (
    DatabaseError,
    DataError,
    Error,
    IntegrityError,
    InterfaceError,
    InternalError,
    NotSupportedError,
    OperationalError,
    ProgrammingError,
)
from turborel._codec.failures import Failure
from turborel._session.capabilities import COMPRESSION, Offer
from turborel._session.raising import ends_connection, raised


def failure(sqlstate: str, sqlcode: int = -1) -> Failure:
    """A failure of `sqlstate`."""
    return Failure(sqlcode, sqlstate, "m", None, None, active=False)


@pytest.mark.parametrize(
    ("sqlstate", "kind"),
    [
        ("08006", OperationalError),
        ("28000", OperationalError),
        ("40001", OperationalError),
        ("TB920", OperationalError),
        ("22003", DataError),
        ("23505", IntegrityError),
        ("0A000", NotSupportedError),
        ("24000", InternalError),
        ("42000", ProgrammingError),
        ("2A000", ProgrammingError),
        ("07006", ProgrammingError),
        ("TB910", InterfaceError),
        ("HY000", DatabaseError),
    ],
)
def test_a_failure_is_raised_by_its_sqlstate_s_class(
    sqlstate: str, kind: type[Error]
) -> None:
    """Verifies: [DESIGN] D9 the exception chosen by the condition, the failure kept."""
    error = raised(failure(sqlstate))
    assert type(error) is kind
    assert error.sqlstate == sqlstate
    assert error.failure == failure(sqlstate)


@pytest.mark.parametrize(
    ("sqlstate", "sqlcode", "ends"),
    [
        ("08006", -919, True),
        ("08004", -919, True),
        ("08003", -919, False),
        ("28000", -919, True),
        ("28000", -104, False),
        ("42000", -919, False),
    ],
)
def test_which_failures_end_the_connection(
    sqlstate: str, sqlcode: int, *, ends: bool
) -> None:
    """Verifies: [PROTOCOL Error 'E'] class 08 but 08003, or 28 at login, ends it."""
    assert ends_connection(failure(sqlstate, sqlcode)) is ends


def test_an_offer_asks_for_compression_and_attributes() -> None:
    """Verifies: [CLIENT What a connection asks for] an offer of the program's own.

    None, compression added once, a connection attribute added.
    """
    offer = Offer()
    assert COMPRESSION not in offer.capabilities
    compressed = offer.compressed()
    assert compressed.compressed() is compressed
    assert compressed.capabilities.count(COMPRESSION) == 1
    assert offer.attribute("application", "x").attributes == (("application", "x"),)
    assert Offer.none().capabilities == ()
