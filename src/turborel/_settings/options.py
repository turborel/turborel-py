"""Settings as text, a layer of them [CLIENT Where settings come from].

A layer is the program's own settings, or a connection URI's, a
service's section of the service file, or the environment's. The layers
are laid one over another, each setting taken from the first that has
it, then read into `Settings`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from turborel._errors import CONNECTION_FAILURE_SQLCODE, OperationalError

if TYPE_CHECKING:
    from collections.abc import Callable

HOST: Final = "host"
PORT: Final = "port"
USER: Final = "user"
PASSWORD: Final = "password"  # noqa: S105  # A setting's name.
TLS_MODE: Final = "tls_mode"
CHANNEL_BINDING: Final = "channel_binding"
APPLICATION_NAME: Final = "application_name"
CONNECT_TIMEOUT: Final = "connect_timeout"
SERVICE: Final = "service"
SERVICE_FILE: Final = "service_file"
PASSFILE: Final = "passfile"
TARGET: Final = "target"
LOAD_BALANCE: Final = "load_balance"
TLS_ROOTS: Final = "tls_roots"
TLS_SYSTEM_ROOTS: Final = "tls_system_roots"
TLS_CERTIFICATE: Final = "tls_certificate"
TLS_KEY: Final = "tls_key"
SERVER_NAME: Final = "server_name"

KEYS: Final = (
    HOST,
    PORT,
    USER,
    PASSWORD,
    TLS_MODE,
    CHANNEL_BINDING,
    APPLICATION_NAME,
    CONNECT_TIMEOUT,
    SERVICE,
    SERVICE_FILE,
    PASSFILE,
    TARGET,
    LOAD_BALANCE,
    TLS_ROOTS,
    TLS_SYSTEM_ROOTS,
    TLS_CERTIFICATE,
    TLS_KEY,
    SERVER_NAME,
)
"""Every setting's name, as the program, a URI's query and a service file write them."""

ENVIRONMENT: Final = (
    ("TURBOREL_HOST", HOST),
    ("TURBOREL_PORT", PORT),
    ("TURBOREL_USER", USER),
    ("TURBOREL_PASSWORD", PASSWORD),
    ("TURBOREL_TLS_MODE", TLS_MODE),
    ("TURBOREL_APPLICATION_NAME", APPLICATION_NAME),
    ("TURBOREL_CONNECT_TIMEOUT", CONNECT_TIMEOUT),
    ("TURBOREL_SERVICE", SERVICE),
    ("TURBOREL_SERVICE_FILE", SERVICE_FILE),
    ("TURBOREL_PASSFILE", PASSFILE),
)
"""The environment's variables, each with the setting it gives."""

UNABLE_TO_CONNECT: Final = "08001"
"""SQLSTATE 08001: the client unable to connect."""


def invalid(message: str) -> OperationalError:
    """A setting that cannot be read, or settings no connection is made by (08001)."""
    return OperationalError(
        message, sqlcode=CONNECTION_FAILURE_SQLCODE, sqlstate=UNABLE_TO_CONNECT
    )


class Options:
    """A layer of connection settings, each by its name."""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        """Settings of `values`, each checked by `set`.

        Raises:
            OperationalError: SQLSTATE 08001, of a name no setting has.
        """
        self._values: dict[str, str] = {}
        for key, value in (values or {}).items():
            self.set(key, value)

    def __repr__(self) -> str:
        """Never the password."""
        shown = {
            k: "..." if k == PASSWORD else v for k, v in sorted(self._values.items())
        }
        return f"Options({shown})"

    def __eq__(self, other: object) -> bool:
        """Whether both set the same settings alike."""
        return isinstance(other, Options) and self._values == other._values

    __hash__ = None  # type: ignore[assignment]  # Mutable.

    def set(self, key: str, value: str) -> Options:
        """Set `key` to `value`; these options, so sets chain.

        Raises:
            OperationalError: SQLSTATE 08001, if `key` names no setting.
        """
        if key not in KEYS:
            msg = f"{key} is no connection setting"
            raise invalid(msg)
        self._values[key] = value
        return self

    def get(self, key: str) -> str | None:
        """The value of `key`, if set."""
        return self._values.get(key)

    def is_empty(self) -> bool:
        """Whether none is set."""
        return not self._values

    def over(self, lower: Options) -> Options:
        """These settings laid over `lower`: each of its kept where these have none."""
        laid = Options()
        laid._values = {**lower._values, **self._values}  # Its kind's.
        return laid

    @classmethod
    def from_uri(cls, uri: str) -> Options:
        """The settings the connection URI `uri` gives [CLIENT The connection URI].

        Raises:
            OperationalError: SQLSTATE 08001, if it is not one.
        """
        from turborel._settings.uri import from_uri  # noqa: PLC0415  # Its own module's.

        return from_uri(uri)

    @classmethod
    def environment(cls, variable: Callable[[str], str | None]) -> Options:
        """The settings the environment gives, `variable` reading each variable.

        An empty variable gives none.
        """
        found = cls()
        for name, key in ENVIRONMENT:
            value = variable(name)
            if value:
                found._values[key] = value  # Its kind's.
        return found
