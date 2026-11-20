"""Data types, as columns and parameters describe them [PROTOCOL Data types].

A data type is a tag, then what its kind writes after it. A distinct
type comes as its source type, and a plug-in's type a client does not
have is read by its name and parameters. The types are read only, since
a client never sends one; each is a frozen dataclass a program can
compare and print.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import TYPE_CHECKING, Final

from turborel._codec import tags

if TYPE_CHECKING:
    from collections.abc import Callable

    from turborel._codec.fields import Reader

MAX_CARDINALITY: Final = 65_535
"""The greatest maximum cardinality of an array type, and of a multiset.

turborel's `MAX_ARRAY_CARDINALITY` (RULES.md D13).
"""

MAX_PLUGIN_PARAMETERS: Final = 2
"""The most parameters a plug-in's type has: turborel's `MAX_PARAMS`."""

_ABSENT_PARAMETER: Final = 0xFFFF_FFFF
# A scope, a namespace or an element: absent, 0, or present, 1, and then it.
_ABSENT: Final = 0
_PRESENT: Final = 1


class IntervalField(IntEnum):
    """An interval's field, numbered as the protocol writes it."""

    YEAR = 0
    MONTH = 1
    DAY = 2
    HOUR = 3
    MINUTE = 4
    SECOND = 5


class Moment(IntEnum):
    """Which fields a datetime has."""

    DATE = 0
    TIME = 1
    TIMESTAMP = 2


class XmlPrimary(IntEnum):
    """An XML type's primary modifier."""

    DOCUMENT = 0
    CONTENT = 1
    SEQUENCE = 2


class XmlSecondary(IntEnum):
    """An XML type's secondary modifier."""

    UNTYPED = 0
    ANY = 1
    XMLSCHEMA = 2


@dataclass(frozen=True, slots=True)
class QualifiedName:
    """A schema object's schema and name."""

    schema: str
    name: str


@dataclass(frozen=True, slots=True)
class Qualifier:
    """An interval's qualifier: its fields and precisions."""

    start: IntervalField
    end: IntervalField
    leading_precision: int
    fractional_precision: int

    @property
    def year_month(self) -> bool:
        """Whether it is of a year-month interval, counted in months."""
        return self.start in (IntervalField.YEAR, IntervalField.MONTH)


@dataclass(frozen=True, slots=True)
class CharacterType:
    """CHARACTER, or CHARACTER VARYING: its length, in characters or octets."""

    varying: bool
    length: int
    octets: bool


@dataclass(frozen=True, slots=True)
class ExactType:
    """An exact numeric type: its precision and scale."""

    precision: int
    scale: int


@dataclass(frozen=True, slots=True)
class ApproximateType:
    """An approximate numeric type: its precision."""

    precision: int


@dataclass(frozen=True, slots=True)
class PluginType:
    """A plug-in's type: its name and parameters."""

    name: str
    parameters: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class BinaryType:
    """BINARY, or BINARY VARYING: its length."""

    varying: bool
    length: int


@dataclass(frozen=True, slots=True)
class DatetimeType:
    """DATE, TIME or TIMESTAMP, WITH TIME ZONE or not: its precision."""

    moment: Moment
    zoned: bool
    precision: int


@dataclass(frozen=True, slots=True)
class IntervalType:
    """INTERVAL: its qualifier."""

    qualifier: Qualifier


@dataclass(frozen=True, slots=True)
class BooleanType:
    """BOOLEAN."""


@dataclass(frozen=True, slots=True)
class DecFloatType:
    """DECFLOAT: its precision."""

    precision: int


@dataclass(frozen=True, slots=True)
class ArrayType:
    """An array type: its maximum cardinality and its element type."""

    max_cardinality: int
    element: DataType


@dataclass(frozen=True, slots=True)
class RowField:
    """A field of a row type: its name and type."""

    name: str
    data_type: DataType


@dataclass(frozen=True, slots=True)
class RowType:
    """A row type: its fields, one or more."""

    fields: tuple[RowField, ...]


@dataclass(frozen=True, slots=True)
class LobType:
    """A large object type, character or binary: its length and units."""

    binary: bool
    length: int
    octets: bool


@dataclass(frozen=True, slots=True)
class MultisetType:
    """A multiset type: its element type."""

    element: DataType


@dataclass(frozen=True, slots=True)
class StructuredType:
    """A structured type: its name and its proper supertypes' names."""

    name: QualifiedName
    supertypes: tuple[QualifiedName, ...]


@dataclass(frozen=True, slots=True)
class ReferenceType:
    """A reference type: the type it references, and its scope if scoped."""

    referenced: StructuredType
    scope: QualifiedName | None


@dataclass(frozen=True, slots=True)
class JsonType:
    """JSON."""


@dataclass(frozen=True, slots=True)
class XmlSchemaName:
    """What an XML type of XMLSCHEMA indicates."""

    schema: str
    name: str
    namespace: str | None
    element: str | None


@dataclass(frozen=True, slots=True)
class XmlType:
    """XML: its modifiers, and of XMLSCHEMA the schema it indicates."""

    primary: XmlPrimary
    secondary: XmlSecondary
    schema: XmlSchemaName | None


@dataclass(frozen=True, slots=True)
class UuidType:
    """UUID (turborel's RULES.md D184)."""


DataType = (
    CharacterType
    | ExactType
    | ApproximateType
    | PluginType
    | BinaryType
    | DatetimeType
    | IntervalType
    | BooleanType
    | DecFloatType
    | ArrayType
    | RowType
    | LobType
    | MultisetType
    | StructuredType
    | ReferenceType
    | JsonType
    | XmlType
    | UuidType
)
"""Any data type a column or a parameter has."""


def read_data_type(r: Reader) -> DataType:
    """The data type `r` holds next: its tag, then its parameters.

    Raises:
        OperationalError: SQLSTATE 08006, of a tag of no type or
            parameters out of range.
    """
    tag = r.u8()
    read = _READERS.get(tag)
    if read is None:
        msg = f"no data type has tag {tag}"
        raise r.malformed(msg)
    return read(r)


def read_units(r: Reader) -> bool:
    """A length's units: whether in octets rather than characters."""
    units = r.u8()
    if units not in (tags.UNITS_CHARACTERS, tags.UNITS_OCTETS):
        msg = f"a length's units are {units}"
        raise r.damaged(msg)
    return units == tags.UNITS_OCTETS


def read_qualifier(r: Reader) -> Qualifier:
    """An interval's qualifier: start, end, leading and fractional precision."""
    start, end, leading, fraction = r.u32(), r.u32(), r.u32(), r.u32()
    fields = {f.value for f in IntervalField}
    if start not in fields or end not in fields:
        msg = "an interval's field is out of range"
        raise r.malformed(msg)
    return Qualifier(IntervalField(start), IntervalField(end), leading, fraction)


def _plugin(r: Reader) -> PluginType:
    name = r.string()
    parameters = tuple(r.items(lambda r: r.u32()))
    if len(parameters) > MAX_PLUGIN_PARAMETERS or _ABSENT_PARAMETER in parameters:
        msg = "a type has too many parameters"
        raise r.malformed(msg)
    return PluginType(name, parameters)


def _datetime(moment: Moment, *, zoned: bool) -> Callable[[Reader], DatetimeType]:
    return lambda r: DatetimeType(moment, zoned=zoned, precision=r.u32())


def _array(r: Reader) -> ArrayType:
    def read(r: Reader) -> ArrayType:
        most = r.u32()
        if not 1 <= most <= MAX_CARDINALITY:
            msg = "an array type's maximum cardinality is out of range"
            raise r.malformed(msg)
        return ArrayType(most, read_data_type(r))

    return r.nested(read)


def _row(r: Reader) -> RowType:
    def read(r: Reader) -> RowType:
        fields = r.items(lambda r: RowField(r.string(), read_data_type(r)))
        if not fields:
            msg = "a row type has no fields"
            raise r.malformed(msg)
        return RowType(tuple(fields))

    return r.nested(read)


def _multiset(r: Reader) -> MultisetType:
    return r.nested(lambda r: MultisetType(read_data_type(r)))


def _name(r: Reader) -> QualifiedName:
    return QualifiedName(r.string(), r.string())


def _structured(r: Reader) -> StructuredType:
    name = _name(r)
    return StructuredType(name, tuple(r.items(_name)))


def _reference(r: Reader) -> ReferenceType:
    referenced = _structured(r)
    scoped = r.u8()
    if scoped not in (_ABSENT, _PRESENT):
        msg = "a reference type's scope flag is neither 0 nor 1"
        raise r.malformed(msg)
    return ReferenceType(referenced, _name(r) if scoped == _PRESENT else None)


def _optional_string(r: Reader) -> str | None:
    marked = r.u8()
    if marked not in (_ABSENT, _PRESENT):
        msg = f"an XML type's namespace or element is marked {marked}"
        raise r.malformed(msg)
    return r.string() if marked == _PRESENT else None


def _xml(r: Reader) -> XmlType:
    primary, secondary = r.u8(), r.u8()
    if primary not in {p.value for p in XmlPrimary}:
        msg = f"an XML type's primary modifier is {primary}"
        raise r.malformed(msg)
    if secondary not in {s.value for s in XmlSecondary}:
        msg = f"an XML type's secondary modifier is {secondary}"
        raise r.malformed(msg)
    sequence = primary == XmlPrimary.SEQUENCE
    if sequence and secondary != XmlSecondary.UNTYPED:
        msg = "an XML type of SEQUENCE is untyped"
        raise r.malformed(msg)
    schema = None
    if secondary == XmlSecondary.XMLSCHEMA:
        schema_name, name = r.string(), r.string()
        namespace = _optional_string(r)
        schema = XmlSchemaName(schema_name, name, namespace, _optional_string(r))
    return XmlType(XmlPrimary(primary), XmlSecondary(secondary), schema)


_READERS: Final[dict[int, Callable[[Reader], DataType]]] = {
    tags.TYPE_CHARACTER: lambda r: CharacterType(
        varying=False, length=r.u32(), octets=read_units(r)
    ),
    tags.TYPE_EXACT: lambda r: ExactType(r.u32(), r.u32()),
    tags.TYPE_APPROXIMATE: lambda r: ApproximateType(r.u32()),
    tags.TYPE_PLUGIN: _plugin,
    tags.TYPE_VARYING: lambda r: CharacterType(
        varying=True, length=r.u32(), octets=read_units(r)
    ),
    tags.TYPE_BINARY: lambda r: BinaryType(varying=False, length=r.u32()),
    tags.TYPE_BINARY_VARYING: lambda r: BinaryType(varying=True, length=r.u32()),
    tags.TYPE_DATE: _datetime(Moment.DATE, zoned=False),
    tags.TYPE_TIME: _datetime(Moment.TIME, zoned=False),
    tags.TYPE_TIME_ZONED: _datetime(Moment.TIME, zoned=True),
    tags.TYPE_TIMESTAMP: _datetime(Moment.TIMESTAMP, zoned=False),
    tags.TYPE_TIMESTAMP_ZONED: _datetime(Moment.TIMESTAMP, zoned=True),
    tags.TYPE_INTERVAL: lambda r: IntervalType(read_qualifier(r)),
    tags.TYPE_BOOLEAN: lambda _: BooleanType(),
    tags.TYPE_DECFLOAT: lambda r: DecFloatType(r.u32()),
    tags.TYPE_ARRAY: _array,
    tags.TYPE_ROW: _row,
    tags.TYPE_CLOB: lambda r: LobType(
        binary=False, length=r.u64(), octets=read_units(r)
    ),
    tags.TYPE_BLOB: lambda r: LobType(
        binary=True, length=r.u64(), octets=read_units(r)
    ),
    tags.TYPE_MULTISET: _multiset,
    tags.TYPE_STRUCTURED: _structured,
    tags.TYPE_REFERENCE: _reference,
    tags.TYPE_JSON: lambda _: JsonType(),
    tags.TYPE_XML: _xml,
    tags.TYPE_UUID: lambda _: UuidType(),
}
