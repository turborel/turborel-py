"""A live server, as the set-up in conftest.py starts it, and its names."""

from __future__ import annotations

from dataclasses import dataclass

OWNER = "ANN"
"""The server's owner, whose certificate the set-up makes."""
PASSWORD = "ann's secret"  # noqa: S105  # The test server's, made for the session.
"""The owner's password."""


@dataclass(frozen=True)
class Live:
    """A live server, and the files a client needs to reach it."""

    host: str
    port: int
    socket: str
    ca: str
    """The PEM file of the authority that signed the server's certificate."""
    client_certificate: str
    """ANN's certificate, signed by the authority the server trusts."""
    client_key: str
    stranger: str
    """The PEM file of an authority no one trusts."""
    user: str = OWNER
    password: str = PASSWORD
