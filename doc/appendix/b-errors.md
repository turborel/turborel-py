# Appendix B: Errors

[Contents](README.md)

A failure reaches a program as one of PEP 249's exceptions, of the
module `turborel`, chosen by its SQLSTATE's class, as this table gives.
Each carries its SQLCODE and SQLSTATE, by which a program tells one
failure from another
([Errors and Diagnostics](../user/10-errors.md)).

## By SQLSTATE class

| Class | What | Exception | Ends the connection |
|---|---|---|---|
| 07 | dynamic SQL error | `ProgrammingError` | |
| 08 | connection exception | `OperationalError` | yes, but 08003 |
| 0A | feature not supported | `NotSupportedError` | |
| 21 | cardinality violation | `ProgrammingError` | |
| 22 | data exception | `DataError` | |
| 23 | integrity constraint violation | `IntegrityError` | |
| 24 | invalid cursor state | `InternalError` | |
| 25 | invalid transaction state | `InternalError` | |
| 26 | invalid SQL statement name | `ProgrammingError` | |
| 27 | triggered data change violation | `OperationalError` | |
| 28 | invalid authorization specification | `OperationalError` | as the connection is made, of SQLCODE -919 |
| 2A | syntax error or access rule violation | `ProgrammingError` | |
| 2B | dependent privilege descriptors still exist | `InternalError` | |
| 2D | invalid transaction termination | `InternalError` | |
| 2E | invalid connection name | `ProgrammingError` | |
| 34 | invalid cursor name | `ProgrammingError` | |
| 3D | invalid catalog name | `ProgrammingError` | |
| 3F | invalid schema name | `ProgrammingError` | |
| 40 | transaction rollback | `OperationalError` | |
| 42 | syntax error or access rule violation | `ProgrammingError` | |
| 44 | with check option violation | `ProgrammingError` | |
| 53 | insufficient resources | `OperationalError` | |
| 54 | program limit exceeded | `OperationalError` | |
| 55 | object not in prerequisite state | `OperationalError` | |
| 57 | operator intervention | `OperationalError` | |
| 58 | system error | `OperationalError` | |
| TB | Turborel's own, TB910 apart | `OperationalError` | |
| TB910 | an interface used wrongly | `InterfaceError` | |
| any other | | `DatabaseError` | |

A failure of the connection's stream, which the driver raises as
SQLCODE -919 and SQLSTATE 08006, ends the connection too.

## Turborel's own SQLSTATEs

| SQLSTATE | SQLCODE | What |
|---|---|---|
| TB910 | -910 | an interface used wrongly |
| TB920 | -920 | a statement cancelled |
| TBR01 | -920 | a replica had not applied the commit position of REPLICATION.READ_AFTER in time |
| 01T01 | | a notice: Reset or ChangeUser rolled back the transaction that was active |

## Raised by the driver

| SQLSTATE | SQLCODE | Exception | When |
|---|---|---|---|
| 08006 | -919 | `OperationalError` | the server cannot be reached; a TLS handshake fails; a wait runs out; a reply cannot be read, is out of turn or is too long; a capability not granted is needed; attributes past their bounds |
| 28000 | -919 | `OperationalError` | a password, or SCRAM, would go over plain TCP |
| 22000 | -301 | `DataError` | a value of a type the protocol cannot carry |
| 22003 | -301 | `DataError` | a number its field cannot hold |
| 22008 | -301 | `DataError` | a datetime its fields cannot hold |
| 2200M | -301 | `DataError` | an XML value's nodes asked for, its text not well-formed |
| 0A000 | -900 | `NotSupportedError` | a value past the protocol's limits |
| 22000 | -301 | `DataError` | a large object held whole freed or held as if by a locator |
| 22000 | -301 | `ImportFailure` | an import whose input cannot be read |
| TB910 | -910 | `InterfaceError` | an interface used wrongly; a request while a copy is under way |

[Errors](../client/30-errors.md) gives each at length.
