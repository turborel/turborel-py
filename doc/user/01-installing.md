# Installing

[Contents](README.md)

This chapter will tell what the driver needs, CPython 3.11 or later on Linux,
macOS or Windows, and how a program takes `turborel` in from
PyPI. No package is published until every Turborel driver is
done; until then the driver is built from its source, as the
repository's
[README](../../README.md)
says. The chapter is written with the standard API, at milestone M7, and
again when the packages are published.

To build it from its source, with
[uv](https://docs.astral.sh/uv/):

```
git clone https://github.com/turborel/turborel-py
cd turborel-py
uv build                   # the sdist and the wheel, in dist/
pip install dist/turborel-0.0.0-py3-none-any.whl
```
