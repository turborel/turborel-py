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
