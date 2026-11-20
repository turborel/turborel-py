"""A data type as SQL writes it, from what its tag and parameters say.

Turborel's `DataType` display, which turborel-client's `type_written`
gives of a column whose declared type it was not told (RULES.md D13). A
tag can stand for several declared types, so an exact numeric type is
written NUMERIC and an approximate one FLOAT, as a type read from a
reply is: INTEGER is NUMERIC(10,0) [PROTOCOL Declared types].
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from turborel._codec.datatypes import (
    ApproximateType,
    ArrayType,
    BinaryType,
    BooleanType,
    CharacterType,
    DatetimeType,
    DecFloatType,
    ExactType,
    IntervalType,
    JsonType,
    LobType,
    Moment,
    MultisetType,
    PluginType,
    QualifiedName,
    ReferenceType,
    RowType,
    StructuredType,
    UuidType,
    XmlSchemaName,
    XmlSecondary,
    XmlType,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from turborel._codec.datatypes import DataType, Qualifier


def written(t: DataType) -> str:
    """`t` as SQL writes it, as Turborel displays a data type."""
    return _WRITERS[type(t)](t)


def _length(name: str, length: int, *, octets: bool) -> str:
    return f"{name}({length} OCTETS)" if octets else f"{name}({length})"


def _character(t: CharacterType) -> str:
    name = "CHARACTER VARYING" if t.varying else "CHARACTER"
    return _length(name, t.length, octets=t.octets)


def _lob(t: LobType) -> str:
    if t.binary:
        return f"BINARY LARGE OBJECT({t.length})"
    return _length("CHARACTER LARGE OBJECT", t.length, octets=t.octets)


def _datetime(t: DatetimeType) -> str:
    if t.moment == Moment.DATE:
        return "DATE"
    name = "TIME" if t.moment == Moment.TIME else "TIMESTAMP"
    return f"{name}({t.precision})" + (" WITH TIME ZONE" if t.zoned else "")


def qualifier_text(q: Qualifier) -> str:
    """An interval's qualifier as SQL writes it: DAY(2) TO SECOND(6)."""
    start, lead, fraction = q.start.name, q.leading_precision, q.fractional_precision
    if q.start == q.end:
        return (
            f"SECOND({lead}, {fraction})"
            if q.end.name == "SECOND"
            else f"{start}({lead})"
        )
    end = f" TO {q.end.name}" + (f"({fraction})" if q.end.name == "SECOND" else "")
    return f"{start}({lead}){end}"


def _name(n: QualifiedName) -> str:
    return f"{n.schema}.{n.name}"


def _reference(t: ReferenceType) -> str:
    referenced = _name(t.referenced.name)
    if t.scope is None:
        return f"REF({referenced})"
    return f"REF({referenced}) SCOPE {_name(t.scope)}"


def _according(s: XmlSchemaName) -> str:
    out = f"ID {s.schema}.{s.name}"
    if s.namespace == "":
        out += " NO NAMESPACE"
    elif s.namespace is not None:
        out += " NAMESPACE '" + s.namespace.replace("'", "''") + "'"
    if s.element is not None:
        out += ' ELEMENT "' + s.element.replace('"', '""') + '"'
    return out


def _xml(t: XmlType) -> str:
    primary = t.primary.name
    if t.schema is not None:
        return f"XML({primary}(XMLSCHEMA {_according(t.schema)}))"
    if primary == "SEQUENCE":
        return "XML(SEQUENCE)"
    return f"XML({primary}({XmlSecondary(t.secondary).name}))"


def _row(t: RowType) -> str:
    return (
        "ROW(" + ", ".join(f"{f.name} {written(f.data_type)}" for f in t.fields) + ")"
    )


_WRITERS: Final[dict[type, Callable[..., str]]] = {
    CharacterType: _character,
    ExactType: lambda t: f"NUMERIC({t.precision},{t.scale})",
    ApproximateType: lambda t: f"FLOAT({t.precision})",
    PluginType: lambda t: t.name,
    BinaryType: lambda t: (
        ("BINARY VARYING" if t.varying else "BINARY") + f"({t.length})"
    ),
    DatetimeType: _datetime,
    IntervalType: lambda t: f"INTERVAL {qualifier_text(t.qualifier)}",
    BooleanType: lambda _: "BOOLEAN",
    DecFloatType: lambda t: f"DECFLOAT({t.precision})",
    ArrayType: lambda t: f"{written(t.element)} ARRAY[{t.max_cardinality}]",
    RowType: _row,
    LobType: _lob,
    MultisetType: lambda t: f"{written(t.element)} MULTISET",
    StructuredType: lambda t: _name(t.name),
    ReferenceType: _reference,
    JsonType: lambda _: "JSON",
    XmlType: _xml,
    UuidType: lambda _: "UUID",
}
