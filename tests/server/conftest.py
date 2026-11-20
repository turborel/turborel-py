"""The live tests' server set-up (RULES.md R-TEST-8).

The live tests run only where `TURBOREL_TEST_SERVER` names the command
that runs `turboreld`, as shell words: the binary itself, or a container
of `ghcr.io/turborel/turborel:nightly` as CI runs it. So the unit tests
stay deterministic and need no server (R-TEST-5).

The set-up makes its own certificates with `openssl` (TURBOREL_TEST_OPENSSL,
else the one on the path): an authority, the server's certificate for
localhost and 127.0.0.1, a client's for ANN, and another authority no one
trusts; so no secret is ever committed. It starts one server for the
session, held in memory, on loopback port 17431 (TURBOREL_TEST_PORT) and
on a Unix socket, with TLS on, the client authority trusted, local
clients trusted, SCRAM taken without TLS too, no delay after a failed
login and few PBKDF2 iterations, its owner ANN with a schema of ANN's;
and stops it at the end.
"""

from __future__ import annotations

import os
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from live import OWNER, PASSWORD, Live

from turborel.client import Trust, connect

if TYPE_CHECKING:
    from collections.abc import Iterator

SERVER = "TURBOREL_TEST_SERVER"
PORT = "TURBOREL_TEST_PORT"
OPENSSL = "TURBOREL_TEST_OPENSSL"
DEFAULT_PORT = 17431
READY_WITHIN = 60.0
CURVE = ("-pkeyopt", "ec_paramgen_curve:prime256v1")


def _openssl(openssl: str, *args: str) -> None:
    subprocess.run([openssl, *args], check=True, capture_output=True)  # noqa: S603  # The test's own.


def _authority(openssl: str, root: Path, name: str) -> tuple[Path, Path]:
    key, cert = root / f"{name}.key", root / f"{name}.pem"
    _openssl(
        openssl, "req", "-x509", "-newkey", "ec", *CURVE, "-nodes",
        "-keyout", str(key), "-out", str(cert), "-days", "2",
        "-subj", f"/CN=turborel test {name}",
        "-addext", "basicConstraints=critical,CA:TRUE",
        "-addext", "keyUsage=critical,keyCertSign,cRLSign",
    )  # fmt: skip
    return key, cert


def _issued(openssl: str, root: Path, name: str, extensions: str) -> tuple[Path, Path]:
    key, request, cert = (
        root / f"{name}.key",
        root / f"{name}.csr",
        root / f"{name}.pem",
    )
    ext = root / f"{name}.ext"
    ext.write_text(extensions, encoding="utf-8")
    _openssl(
        openssl, "req", "-newkey", "ec", *CURVE, "-nodes",
        "-keyout", str(key), "-out", str(request), "-subj", f"/CN={name}",
    )  # fmt: skip
    _openssl(
        openssl, "x509", "-req", "-in", str(request), "-CA", str(root / "ca.pem"),
        "-CAkey", str(root / "ca.key"), "-CAcreateserial", "-out", str(cert),
        "-days", "2", "-extfile", str(ext),
    )  # fmt: skip
    return key, cert


def _certificates(root: Path) -> None:
    openssl = os.environ.get(OPENSSL) or shutil.which("openssl")
    if openssl is None:
        pytest.skip(
            "the live tests make their certificates with openssl, and none is found"
        )
    _authority(openssl, root, "ca")
    _authority(openssl, root, "stranger")
    server = (
        "subjectAltName=DNS:localhost,IP:127.0.0.1\n"
        "extendedKeyUsage=serverAuth\nkeyUsage=critical,digitalSignature\n"
    )
    _issued(openssl, root, "localhost", server)
    client = "extendedKeyUsage=clientAuth\nkeyUsage=critical,digitalSignature\n"
    _issued(openssl, root, OWNER, client)


def _settings(root: Path, port: int) -> list[str]:
    settings = {
        "SERVER.HOST": "127.0.0.1",
        "SERVER.PORT": str(port),
        "SERVER.SOCKET": str(root / "s"),
        "SERVER.TLS": "ON",
        "SERVER.TLS_CERTIFICATE": str(root / "localhost.pem"),
        "SERVER.TLS_KEY": str(root / "localhost.key"),
        "SERVER.TLS_CLIENT_CA": str(root / "ca.pem"),
        "SERVER.TRUST_LOCAL": "ON",
        "SERVER.SCRAM_WITHOUT_TLS": "ON",
        "SERVER.LOGIN_DELAY_MS": "0",
        "SERVER.PASSWORD_ITERATIONS": "10000",
    }
    words = ["--memory", "--owner", OWNER]
    for name, value in settings.items():
        words += ["--set", f"{name}={value}"]
    return words


def _wait(process: subprocess.Popen[bytes], port: int) -> None:
    deadline = time.monotonic() + READY_WITHIN
    while time.monotonic() < deadline:
        if process.poll() is not None:
            pytest.fail(f"turboreld stopped as it started, status {process.returncode}")
        try:
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
        except OSError:
            time.sleep(0.05)
        else:
            return
    pytest.fail(
        f"turboreld did not listen on port {port} within {READY_WITHIN} seconds"
    )


@pytest.fixture(scope="session")
def live() -> Iterator[Live]:
    """The live server, started for the session and stopped after it."""
    command = os.environ.get(SERVER)
    if not command:
        pytest.skip(f"the live tests run where {SERVER} names turboreld's command")
    if sys.platform == "win32":
        pytest.skip("the live set-up starts turboreld on Linux and macOS")
    # A short path: a Unix socket's path is at most about 100 bytes.
    root = Path(tempfile.mkdtemp(prefix="trl", dir="/tmp"))
    _certificates(root)
    port = int(os.environ.get(PORT, DEFAULT_PORT))
    log = (root / "server.log").open("wb")
    process = subprocess.Popen(  # noqa: S603  # The command the test was given.
        [*shlex.split(command), *_settings(root, port)],
        stdin=subprocess.PIPE,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    assert process.stdin is not None
    process.stdin.write(f"{PASSWORD}\n".encode())
    process.stdin.close()
    try:
        _wait(process, port)
        owner = connect(("127.0.0.1", port), OWNER, Trust())
        owner.query(f"CREATE SCHEMA AUTHORIZATION {OWNER}")
        owner.query("COMMIT")
        owner.terminate()
        yield Live(
            "127.0.0.1",
            port,
            str(root / "s"),
            str(root / "ca.pem"),
            str(root / f"{OWNER}.pem"),
            str(root / f"{OWNER}.key"),
            str(root / "stranger.pem"),
        )
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        log.close()
        shutil.rmtree(root, ignore_errors=True)
