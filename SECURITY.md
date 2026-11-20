# Security

Report a vulnerability privately, never in a public issue: on the
repository's **Security** tab, choose **Report a vulnerability**. Only the
maintainers see the report.

What counts, for a driver:

- TLS not used, or not verified, where it was asked for, such as a
  connection under `tls_mode=verify-full` that accepts a certificate of
  another name, or one that falls back to plain TCP;
- a password, a SCRAM key, or a cancel key disclosed: sent where it
  should not be, logged, shown in an exception's message or a `repr`, or
  kept where another program can read it;
- a server's reply, or bytes in the middle of the connection, that
  crash the client, run code in it, or take its memory without bound.

A wrong result, a value decoded wrongly with no attacker, or a crash
only the program's own misuse can cause is a bug: report it with the
**Bug** form, its impact in the title (CONTRIBUTING.md, Reporting
issues). A vulnerability of the server itself goes to
[turborel](https://github.com/turborel/turborel/security).

Say in the report:

- what an attacker needs, such as a server of their own, a place on the
  network, or a user;
- what they gain;
- the commit you tested (`git rev-parse --short=12 HEAD`), and the
  Python version and platform;
- the smallest steps that show it.

You will hear back within a week. The fix is made in private and
published with an advisory that credits you, unless you ask not to be
named.
