r"""The files settings come from: a service file, and a password file.

[CLIENT The service file] holds sections, each `[<name>]` on a line of
its own, then lines `<key> = <value>`, each key a setting's name but
`service` and `service_file`; a line beginning with `#` is a comment,
and blank lines are skipped. [CLIENT The password file] holds lines
`<host>:<port>:<user>:<password>`, a field `*` matching anything, `\\`
taking the character after it as it is, so `\\:` is a colon and `\\\\` a
backslash; the first line that matches is taken, and a line of fewer
fields is skipped.

A password file should be readable by its owner alone. As in
turborel-client, the driver checks only that it is a regular file, or a
link to one, and its owner answers for the rest.
"""

from __future__ import annotations

import os
from typing import Final

from turborel._errors import OperationalError
from turborel._settings.options import SERVICE, SERVICE_FILE, Options, invalid

_COMMENT: Final = "#"
_ANY: Final = "*"
_ESCAPE: Final = "\\"
_SEPARATOR: Final = ":"
_FIELDS: Final = 4


def _lines(text: str) -> list[str]:
    """`text`'s lines, each ended by LF, a CR before it taken off."""
    lines = text.split("\n")
    if lines and not lines[-1]:
        lines.pop()
    return [line.removesuffix("\r") for line in lines]


def service(text: str, name: str, file: str) -> Options:  # noqa: C901  # A case a line.
    """The settings of the section `name` of the service file `text`, read from `file`.

    Raises:
        OperationalError: SQLSTATE 08001, if a line is malformed or sets no
            setting, or there is no section `name`.
    """

    def at(n: int, why: str) -> OperationalError:
        return invalid(f"{file} line {n}: {why}")

    found: Options | None = None
    current: str | None = None
    for n, raw in enumerate(_lines(text), 1):
        line = raw.strip()
        if not line or line.startswith(_COMMENT):
            continue
        if line.startswith("["):
            if not line.endswith("]"):
                raise at(n, "a section's name ends with ]")
            current = line[1:-1].strip()
            continue
        if current is None:
            raise at(n, "a setting comes before any section")
        key, equals, value = line.partition("=")
        if not equals:
            raise at(n, "a setting is <key> = <value>")
        key = key.strip()
        if key in (SERVICE, SERVICE_FILE):
            raise at(n, f"a service cannot set {key}")
        try:
            options = Options().set(key, value.strip())
        except OperationalError as e:
            raise at(n, e.message) from None
        if current == name:
            found = options.over(found or Options())
    if found is None:
        msg = f"{file} has no service {name}"
        raise invalid(msg)
    return found


def read_service(file: str, name: str) -> Options:
    """The settings of the section `name` of the service file at `file`.

    Raises:
        OperationalError: SQLSTATE 08001, if it cannot be read, or as
            `service` raises.
    """
    try:
        with open(file, encoding="utf-8") as f:  # noqa: PTH123  # A path as given.
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        msg = f"cannot read {file}: {e}"
        raise invalid(msg) from None
    return service(text, name, file)


def _fields(line: str) -> list[tuple[str, bool]]:
    """A password line's fields, unescaped, each with whether it was written plain."""
    fields: list[tuple[str, bool]] = []
    field: list[str] = []
    escaped, plain = False, True
    for c in line:
        if escaped:
            field.append(c)
            escaped, plain = False, False
        elif c == _ESCAPE:
            escaped = True
        elif c == _SEPARATOR and len(fields) < _FIELDS - 1:
            fields.append(("".join(field), plain))
            field, plain = [], True
        else:
            field.append(c)
    fields.append(("".join(field), plain))
    return fields


def _matches(field: tuple[str, bool], wanted: str) -> bool:
    value, plain = field
    return (plain and value == _ANY) or value == wanted


def password(text: str, wanted: tuple[str, str, str]) -> str | None:
    """The password the password file `text` gives a host, port and user, if any."""
    host, port, user = wanted
    for line in _lines(text):
        if line.lstrip().startswith(_COMMENT):
            continue
        fields = _fields(line)
        if len(fields) != _FIELDS:
            continue
        h, p, u, (secret, _) = fields
        if _matches(h, host) and _matches(p, port) and _matches(u, user):
            return secret
    return None


def read_regular(path: str) -> str | None:
    """The text at `path`, if a regular file, or a link to one, that can be read."""
    try:
        if not os.path.isfile(path):  # noqa: PTH113  # A path as given.
            return None
        with open(path, encoding="utf-8") as f:  # noqa: PTH123
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None
