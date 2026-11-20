"""The driver's exceptions: PEP 249's hierarchy, each carrying a condition.

Every failure the driver raises is one of these (RULES.md R-ERR-1). Each
carries the SQLCODE, the SQLSTATE and the message the server, or the
driver acting as turborel-client does, gave it, so a program decides by
the SQLSTATE rather than by the exception's class alone (RULES.md D7).
"""

from __future__ import annotations

from typing import Final

# SQLCODE -919 and SQLSTATE 08006, a connection failure: what the server
# and turborel-client give a frame that cannot be read [PROTOCOL Frames].
CONNECTION_FAILURE_SQLCODE: Final = -919
CONNECTION_FAILURE_SQLSTATE: Final = "08006"

# The conditions the driver raises of its own, each turborel's SQLCODE and
# SQLSTATE for it, so a program reads the driver's as it reads the
# server's.
DATA_SQLCODE: Final = -301
"""A data exception, of SQLSTATE class 22."""
NUMERIC_OUT_OF_RANGE: Final = "22003"
"""SQLSTATE 22003: a number its field cannot hold."""
DATETIME_FIELD_OVERFLOW: Final = "22008"
"""SQLSTATE 22008: a datetime its fields cannot hold."""
DYNAMIC_SQLCODE: Final = -921
"""A dynamic SQL error, of SQLSTATE class 07."""
RESTRICTED_DATA_TYPE: Final = "07006"
"""SQLSTATE 07006: a parameter of a type that cannot be sent."""
UNSUPPORTED_SQLCODE: Final = -900
"""Valid, but beyond turborel's limits."""
FEATURE_NOT_SUPPORTED: Final = "0A000"
"""SQLSTATE 0A000."""
API_SQLCODE: Final = -910
"""turborel's SQLCODE for an interface used wrongly."""
API_SQLSTATE: Final = "TB910"
"""turborel's SQLSTATE for an interface used wrongly."""


class _Condition(Exception):  # noqa: N818  # PEP 249 names the subclasses.
    """A condition the driver raises: its SQLCODE, SQLSTATE and message."""

    def __init__(self, message: str, *, sqlcode: int, sqlstate: str) -> None:
        """Make a condition.

        Args:
            message: What went wrong, in plain words.
            sqlcode: The condition's SQLCODE.
            sqlstate: The condition's SQLSTATE, five characters.
        """
        super().__init__(message)
        self.message: Final = message
        self.sqlcode: Final = sqlcode
        self.sqlstate: Final = sqlstate


# PEP 249 names this class `Warning`, which the builtin it stands for in
# this module's namespace shares.
class Warning(_Condition):  # noqa: A001
    """A completion condition of class 01, as PEP 249's Warning."""


class Error(_Condition):
    """The base of every failure the driver raises, as PEP 249's Error."""


class InterfaceError(Error):
    """A failure of the driver rather than of the database."""


class DatabaseError(Error):
    """A failure the database, or the connection to it, reports."""


class DataError(DatabaseError):
    """A value refused: out of range, cut short or not of its type."""


class OperationalError(DatabaseError):
    """A failure of the connection or of the server's operation."""


class IntegrityError(DatabaseError):
    """A constraint refused a change."""


class InternalError(DatabaseError):
    """The database found its own state inconsistent."""


class ProgrammingError(DatabaseError):
    """A statement refused: its syntax, its names or its use."""


class NotSupportedError(DatabaseError):
    """A feature the database or the connection does not offer."""


def connection_failure(message: str) -> OperationalError:
    """A connection failure, SQLCODE -919 and SQLSTATE 08006.

    Args:
        message: Why the connection failed.

    Returns:
        The error to raise.
    """
    return OperationalError(
        message,
        sqlcode=CONNECTION_FAILURE_SQLCODE,
        sqlstate=CONNECTION_FAILURE_SQLSTATE,
    )


def data_error(message: str, sqlstate: str) -> DataError:
    """A value refused before it is sent: SQLCODE -301 and `sqlstate`.

    Args:
        message: Why the value is refused.
        sqlstate: Its SQLSTATE, of class 22.

    Returns:
        The error to raise.
    """
    return DataError(message, sqlcode=DATA_SQLCODE, sqlstate=sqlstate)


def unsendable(message: str) -> ProgrammingError:
    """A parameter of no type the protocol carries: -921 and 07006.

    Args:
        message: What could not be sent.

    Returns:
        The error to raise.
    """
    return ProgrammingError(
        message, sqlcode=DYNAMIC_SQLCODE, sqlstate=RESTRICTED_DATA_TYPE
    )


def beyond_limits(message: str) -> NotSupportedError:
    """A value past turborel's limits, refused before it is sent: -900, 0A000.

    Args:
        message: Which limit.

    Returns:
        The error to raise.
    """
    return NotSupportedError(
        message, sqlcode=UNSUPPORTED_SQLCODE, sqlstate=FEATURE_NOT_SUPPORTED
    )


def misuse(message: str) -> InterfaceError:
    """The driver's interface used wrongly: -910 and TB910.

    Args:
        message: What was wrong.

    Returns:
        The error to raise.
    """
    return InterfaceError(message, sqlcode=API_SQLCODE, sqlstate=API_SQLSTATE)
