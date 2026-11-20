"""The driver's exceptions: PEP 249's hierarchy, each carrying a condition.

Every failure the driver raises is one of these (RULES.md R-ERR-1). Each
carries the SQLCODE, the SQLSTATE and the message the server, or the
driver acting as turborel-client does, gave it, so a program decides by
the SQLSTATE rather than by the exception's class alone (RULES.md D9).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from turborel._codec.failures import Diagnostics, Failure

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
DATA_EXCEPTION: Final = "22000"
"""SQLSTATE 22000: a data exception, as of a value no type of the protocol carries."""
UNSUPPORTED_SQLCODE: Final = -900
"""Valid, but beyond turborel's limits."""
FEATURE_NOT_SUPPORTED: Final = "0A000"
"""SQLSTATE 0A000."""
API_SQLCODE: Final = -910
"""turborel's SQLCODE for an interface used wrongly."""
API_SQLSTATE: Final = "TB910"
"""turborel's SQLSTATE for an interface used wrongly."""


class _Condition(Exception):  # noqa: N818  # PEP 249 names the subclasses.
    """A condition the driver raises: its SQLCODE, SQLSTATE and message.

    One the server sent carries the rest of its failure too: the rule it
    cites, its position, whether a transaction is still active, and its
    diagnostics.
    """

    def __init__(
        self,
        message: str,
        *,
        sqlcode: int,
        sqlstate: str,
        failure: Failure | None = None,
    ) -> None:
        """Make a condition.

        Args:
            message: What went wrong, in plain words.
            sqlcode: The condition's SQLCODE.
            sqlstate: The condition's SQLSTATE, five characters.
            failure: The failure the server sent, if it sent one.
        """
        super().__init__(message)
        self.message: Final = message
        self.sqlcode: Final = sqlcode
        self.sqlstate: Final = sqlstate
        self.failure: Final = failure

    @property
    def rule(self) -> str | None:
        """The rule of a standard the failure cites, if it cites one."""
        return None if self.failure is None else self.failure.rule

    @property
    def position(self) -> int | None:
        """Where in the statement the failure is, in characters, if known."""
        return None if self.failure is None else self.failure.position

    @property
    def transaction_active(self) -> bool | None:
        """Whether the session's transaction is active after it, if the server said."""
        return None if self.failure is None else self.failure.active

    @property
    def diagnostics(self) -> Diagnostics | None:
        """What the failure says beyond its message, with `diagnostics` granted."""
        return None if self.failure is None else self.failure.diagnostics


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


def unsendable(message: str) -> DataError:
    """A parameter of no type the protocol carries: -301 and 22000.

    Args:
        message: What could not be sent.

    Returns:
        The error to raise.
    """
    return DataError(message, sqlcode=DATA_SQLCODE, sqlstate=DATA_EXCEPTION)


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


# The exceptions are the module `turborel`'s, as PEP 249 has them, so a
# traceback names them as a program imports them.
for _exception in (
    Warning,
    Error,
    InterfaceError,
    DatabaseError,
    DataError,
    OperationalError,
    IntegrityError,
    InternalError,
    ProgrammingError,
    NotSupportedError,
):
    _exception.__module__ = "turborel"
