"""The native protocol's codec, version 1, without I/O (RULES.md D1).

Each module encodes and decodes one part of the protocol as
doc/client/05-protocol.md in turborel's repository lays it out, so the
codec is tested byte by byte apart from any connection. It mirrors
turborel-protocol, whose code is right where it and the page differ.
"""
