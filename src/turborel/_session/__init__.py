"""The `session` layer: a connection's session, without I/O (RULES.md D1).

Hello to Ready, the capabilities granted, Status and Notice taken as
they come, ping, reset, change of user and terminate, as turborel-client's
`connection.rs`, `session.rs` and `told.rs` have them. Each request is a
generator that yields what it sends and the replies it waits for, so one
implementation serves the blocking connection and the asyncio one alike.
"""
