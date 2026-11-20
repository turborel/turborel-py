"""Tests of TLS configurations' failures, before any connection is made."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from turborel import OperationalError
from turborel.client import presenting, roots, trusting

if TYPE_CHECKING:
    from pathlib import Path


def test_authorities_that_cannot_be_read_are_refused(tmp_path: Path) -> None:
    """Verifies: [CLIENT Connecting] a file's authorities, or the platform's, trusted.

    A file that cannot be read, one that holds no certificate, or nothing
    trusted at all is refused (08006); the platform's store alone serves.
    """
    with pytest.raises(OperationalError) as missing:
        trusting(str(tmp_path / "none.pem"))
    assert missing.value.sqlstate == "08006"
    empty = tmp_path / "empty.pem"
    empty.write_text("no certificate here\\n", encoding="utf-8")
    with pytest.raises(OperationalError):
        trusting(str(empty))
    with pytest.raises(OperationalError) as nothing:
        roots()
    assert "no certificate authority" in nothing.value.message
    assert roots(platform=True).verify_mode is not None
    with pytest.raises(OperationalError):
        presenting(str(empty), str(empty), str(empty))
