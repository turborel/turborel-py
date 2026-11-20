# Errors

[Contents](README.md)

This page will describe the driver's error: its SQLCODE, SQLSTATE and
message, the rule it cites, its position, whether a transaction is still
active, its diagnostics and its cause; and the failures the driver
raises itself, each with the SQLCODE and SQLSTATE turborel-client gives
it. It is filled at milestone M3.

In Python the driver's error is PEP 249's hierarchy of exceptions,
which the module holds already: each carries `sqlcode`, `sqlstate` and
`message` ([The turborel Module](01-api-module.md)).
