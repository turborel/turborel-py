"""Tests of the package's module globals and its exceptions."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

import turborel
from turborel import _errors

if TYPE_CHECKING:
    from collections.abc import Callable

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def test_the_settled_module_globals() -> None:
    """Verifies: [DESIGN] D2 DB-API 2.0, with the qmark parameter style."""
    assert turborel.apilevel == "2.0"
    assert turborel.paramstyle == "qmark"


def test_the_version_is_the_package_metadata() -> None:
    """Verifies: [DESIGN] D9 one version, 0.0.0, in pyproject.toml and the module."""
    with PYPROJECT.open("rb") as file:
        project = tomllib.load(file)["project"]
    assert turborel.__version__ == project["version"] == "0.0.0"


# PEP 249's hierarchy: each exception and the one it derives from.
HIERARCHY = [
    (turborel.Warning, Exception),
    (turborel.Error, Exception),
    (turborel.InterfaceError, turborel.Error),
    (turborel.DatabaseError, turborel.Error),
    (turborel.DataError, turborel.DatabaseError),
    (turborel.OperationalError, turborel.DatabaseError),
    (turborel.IntegrityError, turborel.DatabaseError),
    (turborel.InternalError, turborel.DatabaseError),
    (turborel.ProgrammingError, turborel.DatabaseError),
    (turborel.NotSupportedError, turborel.DatabaseError),
]


@pytest.mark.parametrize(("exception", "base"), HIERARCHY)
def test_exceptions_follow_pep_249(
    exception: type[turborel.Error | turborel.Warning],
    base: type[Exception],
) -> None:
    """Verifies: [DESIGN] D2 PEP 249's exceptions, each under its base.

    [DESIGN] D7 each carries its SQLCODE, SQLSTATE and message.
    """
    assert issubclass(exception, base)
    raised = exception("refused", sqlcode=-1, sqlstate="HY000")
    assert str(raised) == "refused"
    assert (raised.message, raised.sqlcode, raised.sqlstate) == ("refused", -1, "HY000")


def test_a_warning_is_not_an_error() -> None:
    """Verifies: [DESIGN] D2 PEP 249's Warning stands apart from Error."""
    assert not issubclass(turborel.Warning, turborel.Error)


@pytest.mark.parametrize(
    ("make", "exception", "sqlcode", "sqlstate"),
    [
        (lambda: _errors.data_error("x", "22003"), turborel.DataError, -301, "22003"),
        (lambda: _errors.unsendable("x"), turborel.ProgrammingError, -921, "07006"),
        (lambda: _errors.beyond_limits("x"), turborel.NotSupportedError, -900, "0A000"),
        (lambda: _errors.misuse("x"), turborel.InterfaceError, -910, "TB910"),
        (
            lambda: _errors.connection_failure("x"),
            turborel.OperationalError,
            -919,
            "08006",
        ),
    ],
)
def test_the_driver_raises_turborels_conditions(
    make: Callable[[], turborel.Error],
    exception: type[turborel.Error],
    sqlcode: int,
    sqlstate: str,
) -> None:
    """Verifies: [DESIGN] D14 what the driver refuses itself, by its condition."""
    raised = make()
    assert isinstance(raised, exception)
    assert (raised.sqlcode, raised.sqlstate, raised.message) == (sqlcode, sqlstate, "x")
