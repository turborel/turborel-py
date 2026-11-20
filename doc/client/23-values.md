# Values

[Contents](README.md)

This page will describe the values the low-level client gives and takes
for each of the protocol's types, among them exact numbers, datetimes
and intervals, arrays, rows, multisets and structured values, JSON, XML
and UUIDs; Appendix A maps each to its Python type. It is filled
at milestone M1, and completed at M3.

The codec beneath it is there already: each value the protocol carries
reaches Python, and goes back, as
[Appendix A](../appendix/a-types.md) lists, with the driver's classes
for what Python has no type of its own for: `turborel.DecFloat`,
`Interval`, `Qualifier` and `IntervalField`, `Json`, `Xml`, `Multiset`,
`Structured`, `Reference`, `LargeObject`, `LobLocator` and
`PluginValue`.
