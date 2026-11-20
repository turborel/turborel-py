"""The tags of data types and of values [PROTOCOL Data types] [PROTOCOL Values].

A data type and a value each begin with a tag. The two tables share most
numbers, not all: a value's tag says how it is written, which is not
always its column type's, so a CHARACTER VARYING value is written with
tag 1, as a CHARACTER value is. UUID's tag, 27, is turborel's RULES.md
D184 and `protocol/src/fields.rs`, which the page does not list yet.
"""

from __future__ import annotations

from typing import Final

# --- Data types [PROTOCOL Data types] ---------------------------------------

TYPE_CHARACTER: Final = 1
TYPE_EXACT: Final = 2
TYPE_APPROXIMATE: Final = 3
TYPE_PLUGIN: Final = 4
TYPE_VARYING: Final = 5
TYPE_BINARY: Final = 6
TYPE_BINARY_VARYING: Final = 7
TYPE_DATE: Final = 8
TYPE_TIME: Final = 9
TYPE_TIME_ZONED: Final = 10
TYPE_TIMESTAMP: Final = 11
TYPE_TIMESTAMP_ZONED: Final = 12
TYPE_INTERVAL: Final = 13
TYPE_BOOLEAN: Final = 14
TYPE_DECFLOAT: Final = 15
TYPE_ARRAY: Final = 16
TYPE_ROW: Final = 17
TYPE_CLOB: Final = 18
TYPE_BLOB: Final = 19
TYPE_MULTISET: Final = 22
TYPE_STRUCTURED: Final = 23
TYPE_REFERENCE: Final = 24
TYPE_JSON: Final = 25
TYPE_XML: Final = 26
TYPE_UUID: Final = 27

# --- Values [PROTOCOL Values] -------------------------------------------------

VALUE_NULL: Final = 0
VALUE_CHARACTER: Final = 1
VALUE_EXACT: Final = 2
VALUE_APPROXIMATE: Final = 3
VALUE_PLUGIN: Final = 4
VALUE_BINARY: Final = 6
VALUE_DATE: Final = 8
VALUE_TIME: Final = 9
VALUE_TIMESTAMP: Final = 11
VALUE_INTERVAL: Final = 13
VALUE_BOOLEAN: Final = 14
VALUE_DECFLOAT: Final = 15
VALUE_ARRAY: Final = 16
VALUE_ROW: Final = 17
VALUE_LOB_WHOLE: Final = 20
VALUE_LOB_LOCATOR: Final = 21
VALUE_MULTISET: Final = 22
VALUE_STRUCTURED: Final = 23
VALUE_REFERENCE: Final = 24
VALUE_JSON: Final = 25
VALUE_XML: Final = 26
VALUE_UUID: Final = 27

# turborel-protocol reads these value tags too, each as its type's kind
# writes its values (RULES.md D13): a character string, a binary string, a
# time and a timestamp.
VALUE_VARYING: Final = TYPE_VARYING
VALUE_BINARY_VARYING: Final = TYPE_BINARY_VARYING
VALUE_TIME_ZONED: Final = TYPE_TIME_ZONED
VALUE_TIMESTAMP_ZONED: Final = TYPE_TIMESTAMP_ZONED

# --- Fields within them ------------------------------------------------------

UNITS_CHARACTERS: Final = 0
"""A length in characters, of a character string or large object type."""
UNITS_OCTETS: Final = 1
"""A length in octets."""
LOB_CHARACTER: Final = 0
"""A large object's kind: character."""
LOB_BINARY: Final = 1
"""A large object's kind: binary."""
