r"""The `transport` layer: the streams a connection runs over (RULES.md D1).

TCP, on port 7422 unless told another; a Unix socket, or on Windows the
named pipe `\\.\pipe\turborel`; and TLS begun on the same TCP port; each
bounded by the connect and read timeouts, as turborel-client's
`target.rs`, `timeouts.rs` and `pipe.rs` have them [PROTOCOL The Native
Protocol] [CLIENT Connecting] [CLIENT Timeouts].
"""
