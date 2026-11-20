# Installing

[Contents](README.md)

The driver needs CPython 3.11 or later, on Linux, macOS or Windows, and
nothing else: it is pure Python on the standard library, with no native
code to build and no package it depends on. A program takes it in as the
package `turborel`, from PyPI, once it is published there; no package is
published until every Turborel driver is done, and until then the driver
is built from its source, as the repository's
[README](../../README.md) says.

To build it from its source, with
[uv](https://docs.astral.sh/uv/):

```
git clone https://github.com/turborel/turborel-py
cd turborel-py
uv build                   # the sdist and the wheel, in dist/
pip install dist/turborel-0.0.0-py3-none-any.whl
```

## A first program

The driver's standard interface is DB-API 2.0 (PEP 249). `connect`
takes a `turborel://` URI, or settings by their names; a statement's
parameters are written `?`.

```python
import turborel

with turborel.connect("turborel://ANN@127.0.0.1:7422/") as conn:
    cursor = conn.cursor()
    cursor.execute("VALUES (CURRENT_USER, CAST(? AS VARCHAR(10)))", ("hello",))
    print(cursor.fetchone())
```

```text
('ANN', 'hello')
```

The connection commits as its `with` block ends, and closes. The same
program for asyncio uses `turborel.aio`, its waits awaited. The driver's
version is the Turborel release it comes with, 0.0.0 while it is in
alpha ([Versions](../appendix/d-versions.md)).

## See also

[Connecting](02-connecting.md); [The turborel Module](../client/01-api-module.md).
