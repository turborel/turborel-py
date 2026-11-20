"""A failure the server sent, raised as the driver's exception (RULES.md D9).

The class follows the SQLSTATE's class, as PEP 249 sorts failures: a
connection exception (08), credentials refused (28), a transaction
rolled back (40) or a resource exhausted is an `OperationalError`; a
data exception (22) a `DataError`; an integrity constraint (23) an
`IntegrityError`; a feature not supported (0A) a `NotSupportedError`; an
invalid cursor or transaction state an `InternalError`; syntax, access
and dynamic SQL errors a `ProgrammingError`; turborel's TB910, an
interface used wrongly, an `InterfaceError`. Any other is a
`DatabaseError`. Each keeps the failure whole.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from turborel._errors import (
    API_SQLSTATE,
    CONNECTION_FAILURE_SQLCODE,
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

if TYPE_CHECKING:
    from turborel._codec.failures import Failure

_CLASS_BYTES: Final = 2

# Each SQLSTATE class and the exception of its failures.
_BY_CLASS: Final[dict[str, type[Error]]] = {
    "07": ProgrammingError,
    "08": OperationalError,
    "0A": NotSupportedError,
    "21": ProgrammingError,
    "22": DataError,
    "23": IntegrityError,
    "24": InternalError,
    "25": InternalError,
    "26": ProgrammingError,
    "27": OperationalError,
    "28": OperationalError,
    "2A": ProgrammingError,
    "2B": InternalError,
    "2D": InternalError,
    "2E": ProgrammingError,
    "34": ProgrammingError,
    "3D": ProgrammingError,
    "3F": ProgrammingError,
    "40": OperationalError,
    "42": ProgrammingError,
    "44": ProgrammingError,
    "53": OperationalError,
    "54": OperationalError,
    "55": OperationalError,
    "57": OperationalError,
    "58": OperationalError,
    "TB": OperationalError,
}

CONNECTION_EXCEPTION: Final = "08"
"""SQLSTATE's class of a connection exception."""
NO_CONNECTION: Final = "08003"
"""SQLSTATE 08003: a connection that does not exist, another than this."""
INVALID_AUTHORIZATION: Final = "28"
"""SQLSTATE's class of credentials refused."""


def raised(failure: Failure) -> Error:
    """The driver's exception of `failure`, by its SQLSTATE's class."""
    if failure.sqlstate == API_SQLSTATE:
        kind: type[Error] = InterfaceError
    else:
        kind = _BY_CLASS.get(failure.sqlstate[:_CLASS_BYTES], DatabaseError)
    return kind(
        failure.message,
        sqlcode=failure.sqlcode,
        sqlstate=failure.sqlstate,
        failure=failure,
    )


def ends_connection(failure: Failure) -> bool:
    """Whether the server closes the connection after `failure` [PROTOCOL Error 'E'].

    A connection exception (class 08) but 08003, which names another
    connection; or credentials refused as the connection is made (class
    28, of a connection exception's SQLCODE, -919).
    """
    state = failure.sqlstate
    connecting = state.startswith(INVALID_AUTHORIZATION) and (
        failure.sqlcode == CONNECTION_FAILURE_SQLCODE
    )
    lost = state.startswith(CONNECTION_EXCEPTION) and state != NO_CONNECTION
    return lost or connecting
