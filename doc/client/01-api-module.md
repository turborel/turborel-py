# The turborel Module

[Contents](README.md)

This page will describe the module itself: `connect`, PEP 249's globals `apilevel`, `paramstyle` and `threadsafety`, its type objects and constructors, and its exceptions, part of the driver's
standard interface, DB-API 2.0 (PEP 249), with `?` parameters, and an asyncio interface beside it, `turborel.aio`. It is filled at milestone M7.

Two parts of the module are there already. `apilevel` is `"2.0"` and
`paramstyle` is `"qmark"`, and the module holds PEP 249's exceptions,
`Warning`, `Error`, `InterfaceError`, `DatabaseError`, `DataError`,
`OperationalError`, `IntegrityError`, `InternalError`,
`ProgrammingError` and `NotSupportedError`, each carrying `sqlcode`,
`sqlstate` and `message`.
