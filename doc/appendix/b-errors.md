# Appendix B: Errors

[Contents](README.md)

This appendix will map each SQLSTATE class to the exception the driver
raises for it, under PEP 249's hierarchy. A connection failure, SQLCODE
-919 and SQLSTATE 08006, is an `OperationalError` already; the rest is
filled at milestone M3.
