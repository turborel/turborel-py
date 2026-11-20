"""A value as Turborel writes it as text, and as an SQL literal.

An export writes each value of a row as turborel-client does, by its
type's text: an exact number's digits and its scale's; an approximate
number as `<mantissa>E<exponent>`, its digits the fewest that read back
as it; a binary string's octets in upper case hexadecimal; a datetime by
its fields, its fraction to its type's precision, a zoned one's
displacement after; an interval by its qualifier's fields; a truth value
TRUE or FALSE; JSON as its text; XML as its serialization; a UUID in its
hyphenated form. An array, a row, a multiset, a structured value and a
reference are written as their literals, each part as its own literal.
"""

from __future__ import annotations

import datetime as dt
import math
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Final

from turborel._codec.datatypes import (
    ArrayType,
    DatetimeType,
    DecFloatType,
    IntervalField,
    JsonType,
    Moment,
    MultisetType,
    RowType,
)
from turborel._values import (
    Interval,
    LobLocator,
    Multiset,
    PluginValue,
    Reference,
    Structured,
    Xml,
)

if TYPE_CHECKING:
    from turborel._codec.datatypes import DataType, Qualifier

MICROS: Final = 1_000_000
"""Microseconds in a second."""
_PLAIN_LEAST: Final = -6
"""The least adjusted exponent a DECFLOAT is written plain with."""
_DECFLOAT_DIGITS: Final = 34
"""A DECFLOAT's digits: one of an adjusted exponent of 34 or more takes an exponent."""
_FIELD_MICROS: Final = {
    IntervalField.DAY: 86_400 * MICROS,
    IntervalField.HOUR: 3_600 * MICROS,
    IntervalField.MINUTE: 60 * MICROS,
    IntervalField.SECOND: 1,
}
_FIELD_SPAN: Final = {
    IntervalField.HOUR: 24,
    IntervalField.MINUTE: 60,
    IntervalField.SECOND: 60 * MICROS,
}
_SEPARATOR: Final = {
    IntervalField.MONTH: "-",
    IntervalField.HOUR: " ",
    IntervalField.MINUTE: ":",
    IntervalField.SECOND: ":",
}
_NO_DATETIME_TEXT: Final = (
    "<[ISO/IEC 9075-2:2023 §9.43 GR2a ii] no JSON text parses to a datetime>"
)
_JSON_ESCAPES: Final = {
    '"': '\\"',
    "\\": "\\\\",
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}
_LAST_CONTROL: Final = 0x1F


def _stripped(value: Decimal) -> tuple[int, str, int]:
    """A finite, nonzero number's sign, digits without trailing zeros, and exponent."""
    sign, digits, exponent = value.as_tuple()
    assert isinstance(exponent, int)  # noqa: S101  # A finite number's.
    text = "".join(map(str, digits)).lstrip("0")
    stripped = text.rstrip("0")
    return sign, stripped, exponent + len(text) - len(stripped)


def approximate(x: float) -> str:
    """`x` as Rust's `{:E}` writes it: the fewest digits, `<mantissa>E<exponent>`."""
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "inf" if x > 0 else "-inf"
    sign = "-" if math.copysign(1.0, x) < 0 else ""
    if x == 0:
        return f"{sign}0E0"
    _, text, exponent = _stripped(Decimal(repr(abs(x))))
    mantissa = text[0] + ("." + text[1:] if len(text) > 1 else "")
    return f"{sign}{mantissa}E{exponent + len(text) - 1}"


def approximate_literal(x: float) -> str:
    """`x` as CAST writes it as text: `{:E}`, its mantissa given a point."""
    if x == 0:
        return "0E0"
    text = approximate(x)
    mantissa, _, exponent = text.partition("E")
    if exponent and "." not in mantissa:
        return f"{mantissa}.0E{exponent}"
    return text


def exact(value: int | Decimal) -> str:
    """An exact number's digits and its scale's."""
    return str(value) if isinstance(value, int) else format(value, "f")


def decfloat(value: Decimal) -> str:
    """A DECFLOAT plain, or of an adjusted exponent past its bounds with one."""
    if not value.is_finite():
        return str(value)
    if value.is_zero():
        return "0"
    sign, text, exponent = _stripped(value)
    adjusted = exponent + len(text) - 1
    minus = "-" if sign else ""
    if _PLAIN_LEAST <= adjusted < _DECFLOAT_DIGITS:
        return minus + numeral(text, exponent)
    point = "." if len(text) > 1 else ""
    return f"{minus}{text[0]}{point}{text[1:]}E{adjusted}"


def numeral(digits: str, exponent: int) -> str:
    """`digits` times ten to `exponent`, written without an exponent."""
    if exponent >= 0:
        return digits + "0" * exponent
    padded = digits.rjust(-exponent + 1, "0")
    return f"{padded[:exponent]}.{padded[exponent:]}"


def _displacement(offset: dt.timedelta | None) -> str:
    minutes = int((offset or dt.timedelta()).total_seconds()) // 60
    sign = "-" if minutes < 0 else "+"
    return f"{sign}{abs(minutes) // 60:02}:{abs(minutes) % 60:02}"


def _time_of_day(value: dt.time | dt.datetime, precision: int) -> str:
    text = f"{value.hour:02}:{value.minute:02}:{value.second:02}"
    if precision > 0:
        text += "." + f"{value.microsecond:06}"[:precision]
    if value.tzinfo is not None:
        text += _displacement(value.utcoffset())
    return text


def _precision(value: dt.time | dt.datetime, data_type: DataType | None) -> int:
    if isinstance(data_type, DatetimeType):
        return data_type.precision
    if not value.microsecond:
        return 0
    return len(f"{value.microsecond:06}".rstrip("0"))


def datetime_text(value: dt.date | dt.time, data_type: DataType | None = None) -> str:
    """A date, time or timestamp by its fields, as its type writes it."""
    if isinstance(value, dt.datetime):
        when = f"{value.year:04}-{value.month:02}-{value.day:02}"
        return f"{when} {_time_of_day(value, _precision(value, data_type))}"
    if isinstance(value, dt.time):
        return _time_of_day(value, _precision(value, data_type))
    return f"{value.year:04}-{value.month:02}-{value.day:02}"


def _fields(qualifier: Qualifier) -> list[IntervalField]:
    return [f for f in IntervalField if qualifier.start <= f <= qualifier.end]


def interval(value: Interval) -> str:
    """An interval by its qualifier's fields, a negative one signed."""
    qualifier = value.qualifier
    n = abs(value.units)
    parts = ["-"] if value.units < 0 else []
    for i, field in enumerate(_fields(qualifier)):
        amount = _field_amount(n, field, qualifier.start)
        whole = amount // MICROS if field == IntervalField.SECOND else amount
        parts.append(f"{whole}" if i == 0 else f"{_SEPARATOR[field]}{whole:02}")
        if field == IntervalField.SECOND and qualifier.fractional_precision > 0:
            fraction = f"{amount % MICROS:06}"[: qualifier.fractional_precision]
            parts.append(f".{fraction}")
    return "".join(parts)


def _field_amount(n: int, field: IntervalField, start: IntervalField) -> int:
    if field in (IntervalField.YEAR, IntervalField.MONTH):
        if field == IntervalField.YEAR:
            return n // 12
        return n if start == IntervalField.MONTH else n % 12
    amount = n // _FIELD_MICROS[field] if field != IntervalField.SECOND else n
    if field != start and field in _FIELD_SPAN:
        amount %= _FIELD_SPAN[field]
    return amount


def _qualifier_text(qualifier: Qualifier) -> str:
    start, end = qualifier.start, qualifier.end
    lead, fraction = qualifier.leading_precision, qualifier.fractional_precision
    if start == IntervalField.SECOND:
        return f"SECOND({lead}, {fraction})"
    text = f"{start.name}({lead})"
    if end != start:
        text += f" TO {end.name}" + (
            f"({fraction})" if end == IntervalField.SECOND else ""
        )
    return text


def json_text(value: object) -> str:
    """A JSON value's text, as Turborel serializes it, with no white space."""
    out: list[str] = []
    if not _json(value, out):
        return _NO_DATETIME_TEXT
    return "".join(out)


def _json(value: object, out: list[str]) -> bool:  # noqa: C901  # A case a kind.
    if value is None:
        out.append("null")
    elif isinstance(value, bool):
        out.append("true" if value else "false")
    elif isinstance(value, int | Decimal):
        out.append(exact(value))
    elif isinstance(value, float):
        out.append(approximate_literal(value))
    elif isinstance(value, str):
        out.append(_json_string(value))
    elif isinstance(value, list):
        out.append("[")
        for i, element in enumerate(value):
            out.append("," if i else "")
            if not _json(element, out):
                return False
        out.append("]")
    elif isinstance(value, dict):
        out.append("{")
        for i, (key, member) in enumerate(value.items()):
            out.append(("," if i else "") + _json_string(str(key)) + ":")
            if not _json(member, out):
                return False
        out.append("}")
    else:
        return False
    return True


def _json_string(text: str) -> str:
    escaped = "".join(
        _JSON_ESCAPES.get(c) or (f"\\u{ord(c):04x}" if ord(c) <= _LAST_CONTROL else c)
        for c in text
    )
    return f'"{escaped}"'


def _quoted(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def _element(data_type: DataType | None) -> DataType | None:
    return (
        data_type.element if isinstance(data_type, ArrayType | MultisetType) else None
    )


def _field_types(data_type: DataType | None, n: int) -> list[DataType | None]:
    if isinstance(data_type, RowType):
        return [f.data_type for f in data_type.fields]
    return [None] * n


def text(value: object, data_type: DataType | None = None) -> str:  # noqa: PLR0911, C901, PLR0912  # A case a kind.
    """`value` as Turborel writes it as text, of `data_type` if known; null as NULL."""
    if value is None:
        return "NULL"
    if isinstance(data_type, JsonType):
        return json_text(value)
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, Decimal) and isinstance(data_type, DecFloatType):
        return decfloat(value)
    if isinstance(value, int | Decimal):
        return exact(value)
    if isinstance(value, float):
        return approximate(value)
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        return value.hex().upper()
    if isinstance(value, dt.date | dt.time):
        return datetime_text(value, data_type)
    if isinstance(value, Interval):
        return interval(value)
    if isinstance(value, Xml):
        return value.text
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, PluginValue):
        return value.text
    if isinstance(value, LobLocator):
        if value.binary:
            return f"<BINARY LARGE OBJECT of {value.octets} octets>"
        return f"<CHARACTER LARGE OBJECT of {value.characters} characters>"
    return literal(value, data_type)


def literal(value: object, data_type: DataType | None = None) -> str:  # noqa: PLR0911, C901  # A case a kind.
    """`value` as an SQL literal, as Turborel writes a part of a composite."""
    if value is None:
        return "NULL"
    if isinstance(data_type, JsonType):
        return "JSON(" + _quoted(json_text(value)) + ")"
    if isinstance(value, Decimal) and isinstance(data_type, DecFloatType):
        return f"CAST({_quoted(decfloat(value))} AS DECFLOAT)"
    if isinstance(value, str):
        return _quoted(value)
    if isinstance(value, bytes):
        return f"X'{value.hex().upper()}'"
    if isinstance(value, dt.datetime | dt.time | dt.date):
        word = (
            Moment.TIMESTAMP
            if isinstance(value, dt.datetime)
            else Moment.TIME
            if isinstance(value, dt.time)
            else Moment.DATE
        ).name
        return f"{word} '{datetime_text(value, data_type)}'"
    if isinstance(value, Interval):
        sign = "-" if value.units < 0 else ""
        absolute = Interval(value.qualifier, abs(value.units))
        return (
            f"INTERVAL {sign}'{interval(absolute)}' {_qualifier_text(value.qualifier)}"
        )
    if isinstance(value, Xml):
        return f"XMLPARSE(CONTENT {_quoted(value.text)} PRESERVE WHITESPACE)"
    if isinstance(value, uuid.UUID):
        return f"UUID '{value}'"
    if isinstance(value, PluginValue):
        return f"CAST({_quoted(value.text)} AS {value.type_name})"
    composite = _composite(value, data_type)
    if composite is not None:
        return composite
    return text(value, data_type)


def _composite(value: object, data_type: DataType | None) -> str | None:
    """A composite's literal: an array's, a row's, a structured value's, and so on."""
    if isinstance(value, list):
        element = _element(data_type)
        return "ARRAY[" + ", ".join(literal(v, element) for v in value) + "]"
    if isinstance(value, Multiset):
        element = _element(data_type)
        return (
            "MULTISET[" + ", ".join(literal(v, element) for v in value.elements) + "]"
        )
    if isinstance(value, tuple):
        types = _field_types(data_type, len(value))
        return (
            "ROW("
            + ", ".join(literal(v, t) for v, t in zip(value, types, strict=False))
            + ")"
        )
    if isinstance(value, Structured):
        parts = ", ".join(literal(v) for v in value.attributes)
        return f"{value.schema}.{value.name}({parts})"
    if isinstance(value, Reference):
        return f"REF({value.octets.hex().upper()})"
    return None
