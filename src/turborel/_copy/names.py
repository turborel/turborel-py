"""Names as SQL writes them: a table's, a column's [ISO/IEC 9075:1992 §5.2, §5.4].

An import names its table as SQL does, and its columns as its source's
headings do, each read as Turborel's lexer reads an `<identifier>`: a
`<regular identifier>` in upper case, unless it is a `<key word>`; a
`<delimited identifier>` as written, a quote in it written twice.
"""

from __future__ import annotations

from typing import Final

KEY_WORDS: Final = frozenset(
    (
        "ABSOLUTE",
        "ACTION",
        "ADD",
        "ALL",
        "ALLOCATE",
        "ALTER",
        "AND",
        "ANY",
        "ARE",
        "AS",
        "ASC",
        "ASSERTION",
        "AT",
        "AUTHORIZATION",
        "AVG",
        "BEGIN",
        "BETWEEN",
        "BIT",
        "BIT_LENGTH",
        "BOTH",
        "BY",
        "CASCADE",
        "CASCADED",
        "CASE",
        "CAST",
        "CATALOG",
        "CHAR",
        "CHARACTER",
        "CHAR_LENGTH",
        "CHARACTER_LENGTH",
        "CHECK",
        "CLOSE",
        "COALESCE",
        "COLLATE",
        "COLLATION",
        "COLUMN",
        "COMMIT",
        "CONNECT",
        "CONNECTION",
        "CONSTRAINT",
        "CONSTRAINTS",
        "CONTINUE",
        "CONVERT",
        "CORRESPONDING",
        "COUNT",
        "CREATE",
        "CROSS",
        "CURRENT",
        "CURRENT_DATE",
        "CURRENT_TIME",
        "CURRENT_TIMESTAMP",
        "CURRENT_USER",
        "CURSOR",
        "DATE",
        "DAY",
        "DEALLOCATE",
        "DEC",
        "DECIMAL",
        "DECLARE",
        "DEFAULT",
        "DEFERRABLE",
        "DEFERRED",
        "DELETE",
        "DESC",
        "DESCRIBE",
        "DESCRIPTOR",
        "DIAGNOSTICS",
        "DISCONNECT",
        "DISTINCT",
        "DOMAIN",
        "DOUBLE",
        "DROP",
        "ELSE",
        "END",
        "ESCAPE",
        "EXCEPT",
        "EXCEPTION",
        "EXEC",
        "EXECUTE",
        "EXISTS",
        "EXTERNAL",
        "EXTRACT",
        "FALSE",
        "FETCH",
        "FIRST",
        "FLOAT",
        "FOR",
        "FOREIGN",
        "FOUND",
        "FROM",
        "FULL",
        "GET",
        "GLOBAL",
        "GO",
        "GOTO",
        "GRANT",
        "GROUP",
        "HAVING",
        "HOUR",
        "IDENTITY",
        "IMMEDIATE",
        "IN",
        "INDICATOR",
        "INITIALLY",
        "INNER",
        "INPUT",
        "INSENSITIVE",
        "INSERT",
        "INT",
        "INTEGER",
        "INTERSECT",
        "INTERVAL",
        "INTO",
        "IS",
        "ISOLATION",
        "JOIN",
        "KEY",
        "LANGUAGE",
        "LAST",
        "LEADING",
        "LEFT",
        "LEVEL",
        "LIKE",
        "LOCAL",
        "LOWER",
        "MATCH",
        "MAX",
        "MIN",
        "MINUTE",
        "MODULE",
        "MONTH",
        "NAMES",
        "NATIONAL",
        "NATURAL",
        "NCHAR",
        "NEXT",
        "NO",
        "NOT",
        "NULL",
        "NULLIF",
        "NUMERIC",
        "OCTET_LENGTH",
        "OF",
        "ON",
        "ONLY",
        "OPEN",
        "OPTION",
        "OR",
        "ORDER",
        "OUTER",
        "OUTPUT",
        "OVERLAPS",
        "PAD",
        "PARTIAL",
        "POSITION",
        "PRECISION",
        "PREPARE",
        "PRESERVE",
        "PRIMARY",
        "PRIOR",
        "PRIVILEGES",
        "PROCEDURE",
        "PUBLIC",
        "READ",
        "REAL",
        "REFERENCES",
        "RELATIVE",
        "RESTRICT",
        "REVOKE",
        "RIGHT",
        "ROLLBACK",
        "ROWS",
        "SCHEMA",
        "SCROLL",
        "SECOND",
        "SECTION",
        "SELECT",
        "SESSION",
        "SESSION_USER",
        "SET",
        "SIZE",
        "SMALLINT",
        "SOME",
        "SPACE",
        "SQL",
        "SQLCODE",
        "SQLERROR",
        "SQLSTATE",
        "SUBSTRING",
        "SUM",
        "SYSTEM_USER",
        "TABLE",
        "TEMPORARY",
        "THEN",
        "TIME",
        "TIMESTAMP",
        "TIMEZONE_HOUR",
        "TIMEZONE_MINUTE",
        "TO",
        "TRAILING",
        "TRANSACTION",
        "TRANSLATE",
        "TRANSLATION",
        "TRIM",
        "TRUE",
        "UNION",
        "UNIQUE",
        "UNKNOWN",
        "UPDATE",
        "UPPER",
        "USAGE",
        "USER",
        "USING",
        "VALUE",
        "VALUES",
        "VARCHAR",
        "VARYING",
        "VIEW",
        "WHEN",
        "WHENEVER",
        "WHERE",
        "WITH",
        "WORK",
        "WRITE",
        "YEAR",
        "ZONE",
    )
)
"""Turborel's `<key word>`s, every `<reserved word>`, as its lexer lists them
(`src/lexer.rs` at 1c4187e4): none is a `<regular identifier>`."""

MAX_IDENTIFIER_LENGTH: Final = 128
"""The most characters of an `<identifier>` [ISO/IEC 9075:1992 §5.2 SR8, SR9]."""
MAX_NAME_PARTS: Final = 3
"""The most parts of a `<table name>`: catalog, schema and table."""
_QUOTE: Final = '"'
_PERIOD: Final = "."


class _Wrong(Exception):  # noqa: N818  # A refusal, caught here alone.
    """Text that is not the name wanted."""


def _identifier_part(c: str) -> bool:
    return c.isalpha() or "0" <= c <= "9" or c == "_"


def _tokens(text: str) -> list[tuple[str, str]]:
    """`text`'s tokens: ("identifier", name), ("key word", word) or ("period", ".")."""
    tokens: list[tuple[str, str]] = []
    at = 0
    while at < len(text):
        c = text[at]
        if c.isspace():
            at += 1
        elif c == _PERIOD:
            tokens.append(("period", c))
            at += 1
        elif c == _QUOTE:
            name, at = _delimited(text, at)
            tokens.append(("identifier", name))
        elif c.isalpha():
            end = at + 1
            while end < len(text) and _identifier_part(text[end]):
                end += 1
            word = text[at:end].upper()
            if word in KEY_WORDS:
                tokens.append(("key word", word))
            elif len(text[at:end].replace("_", "")) > MAX_IDENTIFIER_LENGTH:
                raise _Wrong
            else:
                tokens.append(("identifier", word))
            at = end
        else:
            raise _Wrong
    return tokens


def _delimited(text: str, at: int) -> tuple[str, int]:
    """The body of the `<delimited identifier>` at `at`, and where it ends."""
    body: list[str] = []
    at += 1
    while True:
        if at >= len(text) or text[at] in "\r\n":
            raise _Wrong
        c = text[at]
        at += 1
        if c == _QUOTE:
            if text[at : at + 1] != _QUOTE:
                break
            at += 1
        body.append(c)
    if not body or len(body) > MAX_IDENTIFIER_LENGTH:
        raise _Wrong
    return "".join(body), at


def delimited(name: str) -> str:
    """`name` as a `<delimited identifier>`, a quote in it written twice."""
    return _QUOTE + name.replace(_QUOTE, _QUOTE * 2) + _QUOTE


def table_name(text: str) -> str:
    """`text`, a `<table name>`, as SQL text of delimited identifiers.

    So nothing else is taken for one.

    Raises:
        ValueError: If it is not a `<table name>`, saying so.
    """
    wrong = f"[ISO/IEC 9075:1992 §5.4] {text} is not a <table name>"
    try:
        tokens = _tokens(text)
    except _Wrong:
        raise ValueError(wrong) from None
    parts: list[str] = []
    rest = iter(tokens)
    while True:
        token = next(rest, None)
        if token is None or token[0] != "identifier":
            raise ValueError(wrong)
        parts.append(delimited(token[1]))
        following = next(rest, None)
        if following is None:
            return ".".join(parts)
        if following[0] != "period" or len(parts) == MAX_NAME_PARTS:
            raise ValueError(wrong)


def column_name(heading: str) -> str:
    """The column `heading` names.

    The `<identifier>` it is, if it is one, a regular one in upper case;
    a key word as it would be one, but for being reserved; else its name
    as written.
    """
    try:
        tokens = _tokens(heading)
    except _Wrong:
        return heading
    if len(tokens) == 1 and tokens[0][0] in ("identifier", "key word"):
        return tokens[0][1]
    return heading
