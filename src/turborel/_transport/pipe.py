"""A Windows named pipe, opened as turborel-client's `pipe.rs` opens it.

It is opened for SECURITY_IDENTIFICATION alone, as turborel-client's is,
so a server at the pipe's end may learn who the client is but never act
as it; Python's `open` would grant impersonation, so the pipe is opened
by CreateFileW through `ctypes`, on the standard library.

Every instance of a pipe may be busy serving other clients, and opening
one then fails with ERROR_PIPE_BUSY: the client tries again, every 10
milliseconds, within its connect timeout. A pipe is bounded only as it
is opened; its reads and writes wait as long as they must
[CLIENT Timeouts].
"""

from __future__ import annotations

import sys
import time
from typing import IO, TYPE_CHECKING, Final, TypeVar

from turborel._errors import connection_failure

if TYPE_CHECKING:
    from collections.abc import Callable

ERROR_PIPE_BUSY: Final = 231
"""Windows' error of a pipe whose every instance is busy."""

BUSY_RETRY: Final = 0.010
"""The seconds between tries of a busy pipe."""

_T = TypeVar("_T")


def retried(
    open_: Callable[[], _T],
    within: float | None,
    clock: Callable[[], float] = time.monotonic,
    wait: Callable[[float], None] = time.sleep,
) -> _T:
    """What `open_` opens, tried again while the pipe is busy, within `within`.

    Raises:
        TimeoutError: If every instance stays busy past `within` seconds.
        OSError: Any other error `open_` raises, at once.
    """
    began = clock()
    while True:
        try:
            return open_()
        except OSError as e:
            if getattr(e, "winerror", None) != ERROR_PIPE_BUSY:
                raise
            if within is not None and clock() - began >= within:
                msg = f"every instance of the pipe is busy ({e})"
                raise TimeoutError(msg) from e
        wait(BUSY_RETRY)


def open_pipe(path: str, within: float | None) -> IO[bytes]:
    """The named pipe `path`, opened for reading and writing, unbuffered.

    Raises:
        OperationalError: SQLSTATE 08006, on a platform with no named pipes.
        OSError: As opening fails.
    """
    return retried(lambda: _create(path), within)


if sys.platform == "win32":
    import ctypes
    import msvcrt
    import os
    from ctypes import wintypes

    _GENERIC_READ: Final = 0x8000_0000
    _GENERIC_WRITE: Final = 0x4000_0000
    _OPEN_EXISTING: Final = 3
    _SECURITY_SQOS_PRESENT: Final = 0x0010_0000
    _SECURITY_IDENTIFICATION: Final = 0x0001_0000
    _INVALID_HANDLE: Final = wintypes.HANDLE(-1).value

    def _create(path: str) -> IO[bytes]:
        """CreateFileW of the pipe, for identification alone, as a file."""
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        create = kernel32.CreateFileW
        create.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        create.restype = wintypes.HANDLE
        access = _GENERIC_READ | _GENERIC_WRITE
        flags = _SECURITY_SQOS_PRESENT | _SECURITY_IDENTIFICATION
        handle = create(path, access, 0, None, _OPEN_EXISTING, flags, None)
        if handle in (None, _INVALID_HANDLE):
            code = ctypes.get_last_error()
            raise OSError(None, ctypes.FormatError(code), path, code)
        descriptor = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
        return os.fdopen(descriptor, "r+b", buffering=0)

else:

    def _create(path: str) -> IO[bytes]:
        """Refused: a platform other than Windows has no named pipes."""
        msg = f"{path} names a named pipe, and only Windows has them"
        raise connection_failure(msg)
