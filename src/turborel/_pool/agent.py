"""An SQL-agent: a program's connections, named, one current [CLIENT The SQL-agent].

[ISO/IEC 9075:1992 §15] The statements that make, choose and end a
connection, CONNECT, SET CONNECTION and DISCONNECT, the agent runs
itself; every other statement goes to the current connection's session.
A connector makes a connection to the server an address names, as the
user a statement names, proved as the program says. The connection
statements are read as Turborel's parser reads them, each name a
character string literal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Protocol

from turborel._codec.failures import Diagnostics, Failure
from turborel._codec.replies import Complete
from turborel._copy.names import KEY_WORDS, MAX_IDENTIFIER_LENGTH
from turborel._errors import CONNECTION_FAILURE_SQLSTATE, Error
from turborel._session.raising import raised

if TYPE_CHECKING:
    from turborel._client.cancel import Canceller
    from turborel._client.connection import Connection
    from turborel._statements.queries import Outcome, Sink

LEXICAL_SQLCODE: Final = -101
SYNTAX_SQLCODE: Final = -102
SYNTAX_RULE_SQLCODE: Final = -103
PRIVILEGE_SQLCODE: Final = -104
CONNECTION_SQLCODE: Final = -919
UNSUPPORTED_SQLCODE: Final = -900
TRANSACTION_STATE_SQLCODE: Final = -917
SYNTAX_ERROR: Final = "42000"
"""SQLSTATE 42000: a syntax error or access rule violation, run or prepared."""
UNABLE_TO_CONNECT: Final = "08001"
CONNECTION_NAME_IN_USE: Final = "08002"
CONNECTION_DOES_NOT_EXIST: Final = "08003"
CONNECTION_REJECTED: Final = "08004"
MULTIPLE_SERVER_TRANSACTIONS: Final = "0A001"
INVALID_AUTHORIZATION: Final = "28000"
INVALID_CONNECTION_NAME: Final = "2E000"
INVALID_TRANSACTION_STATE: Final = "25000"
DISCONNECT_ERROR: Final = "01002"
"""SQLSTATE 01002: a warning, of a connection DISCONNECT could not end cleanly."""
SUCCESSFUL_COMPLETION: Final = "00000"
_SECTION: Final = "ISO/IEC 9075:1992 §15"


class Connector(Protocol):
    """What makes an agent's connections."""

    def __call__(self, server: str | None, user: str | None) -> Connection:
        """A connection to the server `server` names, as `user`; None for the defaults.

        Raises:
            Error: If the server cannot be reached, or refuses.
        """
        ...


def condition(
    sqlcode: int,
    sqlstate: str,
    message: str,
    rule: str | None = None,
    position: int | None = None,
) -> Error:
    """The error of a condition the agent raises, as Turborel's own would be."""
    failure = Failure(
        sqlcode,
        sqlstate,
        message,
        rule,
        position,
        active=False,
        diagnostics=Diagnostics(severity="ERROR"),
    )
    return raised(failure)


def _exception(sqlstate: str, message: str, rule: str | None = None) -> Error:
    if sqlstate.startswith("28"):
        code = PRIVILEGE_SQLCODE
    elif sqlstate.startswith("0A"):
        code = UNSUPPORTED_SQLCODE
    else:
        code = CONNECTION_SQLCODE
    return condition(code, sqlstate, message, rule)


@dataclass(frozen=True, slots=True)
class _Token:
    kind: str
    """key word, identifier, character, literal, delimiter or end."""
    text: str
    at: int

    def described(self) -> str:
        if self.kind == "character":
            return f"'{self.text}'"
        if self.kind == "delimiter":
            return f'"{self.text}"'
        if self.kind == "end":
            return "end of statement"
        return self.text


def _quoted(src: str, at: int, quote: str) -> tuple[str, int]:
    """What `quote` encloses at `at`, a quote in it written twice, and where it ends."""
    body: list[str] = []
    start = at
    at += 1
    what = "<delimited identifier>" if quote == '"' else "<character string literal>"
    while True:
        if at >= len(src):
            msg = f"unterminated {what}"
            raise condition(
                LEXICAL_SQLCODE, SYNTAX_ERROR, msg, "ISO/IEC 9075:1992 §5.2", start
            )
        c = src[at]
        at += 1
        if c == quote:
            if src[at : at + 1] != quote:
                return "".join(body), at
            at += 1
        body.append(c)


def _word(src: str, at: int) -> tuple[_Token, int]:
    """The key word or regular identifier at `at`, in upper case, and where it ends."""
    end = at + 1
    while end < len(src) and (
        src[end].isalpha() or "0" <= src[end] <= "9" or src[end] == "_"
    ):
        end += 1
    word = src[at:end].upper()
    return _Token("key word" if word in KEY_WORDS else "identifier", word, at), end


def _number_end(src: str, at: int) -> int:
    """Where the numeric literal at `at` ends."""
    end = at + 1
    while end < len(src) and (src[end].isdigit() or src[end] in ".Ee"):
        end += 1
    return end


def _tokens(src: str) -> list[_Token]:  # A case a token.
    """`src`'s tokens, as far as a connection statement needs them told apart."""
    found: list[_Token] = []
    at = 0
    while at < len(src):
        c = src[at]
        if c.isspace():
            at += 1
        elif src.startswith("--", at):
            end = src.find("\n", at)
            at = len(src) if end < 0 else end
        elif src.startswith("/*", at):
            end = src.find("*/", at + 2)
            at = len(src) if end < 0 else end + 2
        elif c == "'":
            body, end = _quoted(src, at, "'")
            found.append(_Token("character", body, at))
            at = end
        elif c in "NnXx" and src[at + 1 : at + 2] == "'":
            body, end = _quoted(src, at + 1, "'")
            kind = "character" if c in "Nn" else "literal"
            found.append(
                _Token(kind, body if kind == "character" else f"X'{body}'", at)
            )
            at = end
        elif c == '"':
            body, end = _quoted(src, at, '"')
            found.append(_Token("identifier", body, at))
            at = end
        elif c.isalpha():
            token, at = _word(src, at)
            found.append(token)
        elif "0" <= c <= "9" or (c == "." and "0" <= src[at + 1 : at + 2] <= "9"):
            end = _number_end(src, at)
            found.append(_Token("literal", src[at:end], at))
            at = end
        else:
            two = src[at : at + 2]
            width = 2 if two in ("||", "<>", "<=", ">=", "->", "=>", "::") else 1
            found.append(_Token("delimiter", src[at : at + width], at))
            at += width
    found.append(_Token("end", "", len(src)))
    return found


@dataclass(frozen=True, slots=True)
class Statement:
    """A connection statement: what it does, and the names it gives."""

    verb: str
    """connect, connect default, set, or disconnect."""
    server: _Token | None = None
    name: _Token | None = None
    user: _Token | None = None
    target: str = ""
    """Of DISCONNECT: default, all, current or named."""


class _Parser:
    def __init__(self, src: str) -> None:
        self.tokens = _tokens(src)
        self.at = 0

    def peek(self) -> _Token:
        return self.tokens[self.at]

    def accept(self, word: str) -> bool:
        token = self.peek()
        if token.kind == "key word" and token.text == word:
            self.at += 1
            return True
        return False

    def syntax(self, expected: str) -> Error:
        token = self.peek()
        message = f"{expected}, found {token.described()}"
        return condition(SYNTAX_SQLCODE, SYNTAX_ERROR, message, position=token.at)

    def expect(self, word: str) -> None:
        if not self.accept(word):
            raise self.syntax(f"expected {word}")

    def literal(self) -> _Token:
        token = self.peek()
        if token.kind not in ("character", "literal"):
            raise self.syntax("expected a <literal>")
        self.at += 1
        return token

    def end(self) -> None:
        token = self.peek()
        if token.kind == "delimiter" and token.text == ";":
            self.at += 1
        if self.peek().kind != "end":
            raise self.syntax("expected end of statement")


def parse(src: str) -> Statement | None:  # noqa: PLR0911  # A return a statement.
    """`src` read as a connection statement; None if it is another.

    Raises:
        Error: SQLCODE -102, SQLSTATE 42000, of one that breaks its syntax.
    """
    parser = _Parser(src)
    first, second = (
        parser.tokens[0],
        parser.tokens[1] if len(parser.tokens) > 1 else None,
    )
    is_word = first.kind == "key word"
    if not is_word or first.text not in ("CONNECT", "DISCONNECT", "SET"):
        return None
    if first.text == "SET":
        if second is None or second.kind != "key word" or second.text != "CONNECTION":
            return None
        parser.at = 2
        name = None if parser.accept("DEFAULT") else parser.literal()
        parser.end()
        return Statement("set", name=name)
    if first.text == "CONNECT":
        parser.at = 1
        parser.expect("TO")
        if parser.accept("DEFAULT"):
            parser.end()
            return Statement("connect default")
        server = parser.literal()
        name = parser.literal() if parser.accept("AS") else None
        user = parser.literal() if parser.accept("USER") else None
        parser.end()
        return Statement("connect", server=server, name=name, user=user)
    parser.at = 1
    for word, target in (
        ("DEFAULT", "default"),
        ("ALL", "all"),
        ("CURRENT", "current"),
    ):
        if parser.accept(word):
            parser.end()
            return Statement("disconnect", target=target)
    named = parser.literal()
    parser.end()
    return Statement("disconnect", name=named, target="named")


def text(token: _Token) -> str:
    """The character string a name is, its spaces trimmed [§15.1 GR2, GR6].

    Raises:
        Error: SQLCODE -103, SQLSTATE 42000, of a literal of another kind.
    """
    if token.kind != "character":
        msg = "a client's connection statement names by character string literals"
        raise condition(SYNTAX_RULE_SQLCODE, SYNTAX_ERROR, msg)
    return token.text.strip(" ")


def identifier(name: str) -> str | None:
    """`name` as an `<identifier>`, if it is one, a regular one upper case."""
    try:
        tokens = _tokens(name)
    except Error:
        return None
    if len(tokens) != 2 or tokens[0].kind != "identifier":  # noqa: PLR2004  # It and the end.
        return None
    found = tokens[0]
    if (
        name.strip()[:1] != '"'
        and len(found.text.replace("_", "")) > MAX_IDENTIFIER_LENGTH
    ):
        return None
    return found.text


def _done(sqlstate: str) -> Complete:
    return Complete(
        sqlcode=0,
        sqlstate=sqlstate,
        active=False,
        position=None,
        more=False,
        rows=None,
        generated=(),
        conditions=(),
        time=None,
    )


@dataclass(slots=True)
class _Held:
    name: str | None
    connection: Connection


class Agent:
    """An SQL-agent's connections, each named, one current."""

    def __init__(
        self, connector: Connector, connection: Connection | None = None
    ) -> None:
        """An agent making its connections by `connector`.

        With `connection`, it is the default connection, current, as a
        client begins connected.
        """
        self._connector = connector
        self._held: list[_Held] = (
            [] if connection is None else [_Held(None, connection)]
        )
        self._current: int | None = None if connection is None else 0

    def current(self) -> Connection:
        """The current connection.

        Raises:
            OperationalError: SQLSTATE 08003, if there is none.
        """
        if self._current is None:
            msg = "there is no current connection"
            raise _exception(CONNECTION_DOES_NOT_EXIST, msg, f"{_SECTION}.3 GR9")
        return self._held[self._current].connection

    @property
    def current_connection(self) -> Connection | None:
        """The current connection, if any, to read what its server last told it."""
        return None if self._current is None else self._held[self._current].connection

    @property
    def current_name(self) -> str | None:
        """The current connection's name; None of the default one, or of none."""
        return None if self._current is None else self._held[self._current].name

    def canceller(self) -> Canceller | None:
        """What cancels the current connection's statement, if any."""
        held = self.current_connection
        return None if held is None else held.canceller()

    @property
    def warning(self) -> str | None:
        """The SQLSTATE of the warning the current connection's last statement gave."""
        held = self.current_connection
        return None if held is None else held.warning

    @property
    def is_lost(self) -> bool:
        """Whether the current connection is lost; with none, not."""
        held = self.current_connection
        return held is not None and held.is_lost

    def query(self, sql: str) -> Outcome:
        """Run `sql`: a connection statement itself; another in the current session.

        Raises:
            Error: The connection statement's, or the statement's.
        """
        done = self.connection_statement(sql)
        if done is not None:
            return done
        return self.current().query(sql)

    def query_into(self, sql: str, sink: Sink) -> int | Complete:
        """Run `sql` as `query` does, a query's rows given to `sink`.

        Raises:
            Error: As `query` raises.
        """
        done = self.connection_statement(sql)
        if done is not None:
            return done
        return self.current().query_into(sql, sink)

    def connection_statement(self, sql: str) -> Complete | None:
        """`sql`, if a connection statement, run: its completion; None of another.

        Raises:
            Error: The statement's, as each rule of §15 says.
        """
        statement = parse(sql)
        if statement is None:
            return None
        if statement.verb == "connect default":
            return self._connect(None, None, None)
        if statement.verb == "connect":
            return self._connect(statement.server, statement.name, statement.user)
        if statement.verb == "set":
            return self._set(statement.name)
        return self._disconnect(statement)

    def _not_in_transaction(self) -> None:
        held = self.current_connection
        if held is not None and held.in_transaction:
            msg = (
                "the current connection's transaction is active, and none spans servers"
            )
            raise _exception(
                MULTIPLE_SERVER_TRANSACTIONS, msg, f"{_SECTION}.1 GR1, §15.2 GR1"
            )

    def _find(self, name: str | None) -> int | None:
        for i, held in enumerate(self._held):
            if held.name == name:
                return i
        return None

    def _connect(
        self, server: _Token | None, name: _Token | None, user: _Token | None
    ) -> Complete:
        self._not_in_transaction()
        who = None if user is None else text(user)
        if who is not None and identifier(who) is None:
            msg = f"'{who}' is not an <authorization identifier>"
            raise _exception(INVALID_AUTHORIZATION, msg, f"{_SECTION}.1 GR3")
        address = None if server is None else text(server)
        named = text(name) if name is not None else address
        identified = None
        if named is not None:
            identified = identifier(named)
            if identified is None:
                msg = f"'{named}' is not an <identifier>"
                raise _exception(INVALID_CONNECTION_NAME, msg, f"{_SECTION}.1 GR6")
        if self._find(identified) is not None:
            what = (
                "the default connection"
                if identified is None
                else f"the connection {identified}"
            )
            raise _exception(
                CONNECTION_NAME_IN_USE, f"{what} is established", f"{_SECTION}.1 GR7"
            )
        try:
            connection = self._connector(address, who)
        except Error as e:
            state = (
                UNABLE_TO_CONNECT
                if e.sqlstate == CONNECTION_FAILURE_SQLSTATE
                else CONNECTION_REJECTED
            )
            raise _exception(state, e.message, f"{_SECTION}.1 GR10, GR11") from e
        self._held.append(_Held(identified, connection))
        self._current = len(self._held) - 1
        return _done(SUCCESSFUL_COMPLETION)

    def _set(self, name: _Token | None) -> Complete:
        self._not_in_transaction()
        wanted = None
        if name is not None:
            given = text(name)
            wanted = identifier(given) or given
        index = self._find(wanted)
        if index is None:
            what = (
                "no default connection" if wanted is None else f"no connection {wanted}"
            )
            raise _exception(
                CONNECTION_DOES_NOT_EXIST, f"there is {what}", f"{_SECTION}.2 GR2"
            )
        self._current = index
        return _done(SUCCESSFUL_COMPLETION)

    def _disconnect(self, statement: Statement) -> Complete:
        rule = f"{_SECTION}.3 GR1-GR3"
        if statement.target == "all":
            ended = list(range(len(self._held)))
        elif statement.target == "current":
            if self._current is None:
                raise _exception(
                    CONNECTION_DOES_NOT_EXIST, "there is no current connection", rule
                )
            ended = [self._current]
        else:
            wanted = None
            if statement.name is not None:
                given = text(statement.name)
                wanted = identifier(given) or given
            index = self._find(wanted)
            if index is None:
                what = (
                    "no default connection"
                    if wanted is None
                    else f"no connection {wanted}"
                )
                raise _exception(CONNECTION_DOES_NOT_EXIST, f"there is {what}", rule)
            ended = [index]
        if any(self._held[i].connection.in_transaction for i in ended):
            msg = "a connection's transaction is active"
            raise condition(
                TRANSACTION_STATE_SQLCODE,
                INVALID_TRANSACTION_STATE,
                msg,
                f"{_SECTION}.3 GR6",
            )
        current = None if self._current is None else self._held[self._current].name
        had_current = self._current is not None
        warned = False
        kept: list[_Held] = []
        for i, held in enumerate(self._held):
            if i in ended:
                try:
                    held.connection.terminate()
                except Error:
                    warned = True
            else:
                kept.append(held)
        self._held = kept
        self._current = self._find(current) if had_current else None
        return _done(DISCONNECT_ERROR if warned else SUCCESSFUL_COMPLETION)

    def terminate(self) -> None:
        """End every connection, as the client ends.

        Raises:
            Error: The first failure ending one; every one is ended still.
        """
        first: Error | None = None
        for held in self._held:
            try:
                held.connection.terminate()
            except Error as e:
                first = first or e
        self._held, self._current = [], None
        if first is not None:
            raise first
