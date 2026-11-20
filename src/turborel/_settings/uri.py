"""A connection URI, read into options [CLIENT The connection URI].

    turborel://[<user>[:<password>]@][<host>[:<port>][,<host>[:<port>]]...][/][?<key>=<value>[&<key>=<value>]...]

Its user, password, hosts and values are percent-encoded (RFC 3986
§2.1), so a host `%2Frun%2Fturborel.sock` names a Unix socket, and an
IPv6 address is written in brackets (RFC 3986 §3.2.2). Each key is a
setting's name. A server serves one database, so the URI names none,
and its path is empty, or `/` alone.
"""

from __future__ import annotations

from typing import Final

from turborel._settings.options import HOST, PASSWORD, USER, Options, invalid

SCHEME: Final = "turborel://"
"""What a connection URI begins with."""
_HEX: Final = "0123456789abcdefABCDEF"


def decode(text: str) -> str:
    """`text` percent-decoded, as UTF-8.

    Raises:
        OperationalError: SQLSTATE 08001, if a `%` is not followed by two
            hexadecimal digits, or the octets are not UTF-8.
    """
    octets = bytearray()
    raw = text.encode("utf-8")
    at = 0
    while at < len(raw):
        b = raw[at]
        at += 1
        if b != ord("%"):
            octets.append(b)
            continue
        digits = raw[at : at + 2].decode("ascii", "replace")
        if len(digits) != 2 or any(d not in _HEX for d in digits):  # noqa: PLR2004  # Two digits.
            msg = f"{text} has a % without two hexadecimal digits"
            raise invalid(msg)
        octets.append(int(digits, 16))
        at += 2
    try:
        return octets.decode("utf-8")
    except UnicodeDecodeError:
        msg = f"{text} is not UTF-8 once decoded"
        raise invalid(msg) from None


def from_uri(uri: str) -> Options:
    """The settings the connection URI `uri` gives.

    Raises:
        OperationalError: SQLSTATE 08001, if it is not one: another scheme,
            a path, a key that names no setting, a pair without `=`, or bad
            percent-encoding.
    """
    if not uri.startswith(SCHEME):
        msg = f"a connection URI begins with {SCHEME}"
        raise invalid(msg)
    rest = uri[len(SCHEME) :]
    before, _, query = rest.partition("?")
    authority, _, path = before.partition("/")
    if path:
        msg = f"a connection URI names no database, so has no path, not /{path}"
        raise invalid(msg)
    options = Options()
    userinfo, at, hosts = authority.rpartition("@")
    if not at:
        userinfo, hosts = "", authority
    if userinfo:
        user, colon, password = userinfo.partition(":")
        options.set(USER, decode(user))
        if colon:
            options.set(PASSWORD, decode(password))
    if hosts:
        options.set(HOST, decode(hosts))
    for pair in (p for p in query.split("&") if p):
        key, equals, value = pair.partition("=")
        if not equals:
            msg = f"{pair} in a connection URI has no ="
            raise invalid(msg)
        options.set(decode(key), decode(value))
    return options
