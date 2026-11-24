"""Tests of the debugger's messages: a frame not visible, and what is malformed."""

from __future__ import annotations

import pytest
from tests.kit import text, u32

from turborel import OperationalError
from turborel._codec.debug import Event, EventKind, Frame, Origin, Pause, RoutineKind
from turborel._codec.replies import decode, ends_request

HIDDEN = (
    b"\x01\x01" + text("BOB") + text("F_1") + text("BOB") + text("F")
    + b"\x00\x00\x00" + u32(0) + u32(0) + u32(0)
)  # fmt: skip
"""A frame of a function the debugger may not see into: its origin alone."""


def test_a_frame_not_visible_shows_its_origin_alone() -> None:
    """Verifies: [PROTOCOL Event 'W'] a frame not visible, of no place, line or names.

    Paused by a step, no breakpoint's number; its frames the outermost
    first; a frame of a statement run directly with no origin.
    """
    direct = b"\x00\x01\x00\x00" + u32(0) + u32(0) + u32(0)
    event = decode(ord("W"), b"\x00\x01" + u32(2) + direct + HIDDEN)
    origin = Origin(RoutineKind.FUNCTION, "BOB", "F_1", "BOB", "F")
    assert event == Event(
        EventKind.PAUSED,
        Pause(
            None,
            (
                Frame(
                    None,
                    visible=True,
                    place=None,
                    line=None,
                    column=None,
                    parameters=(),
                    variables=(),
                    cursors=(),
                ),
                Frame(
                    origin,
                    visible=False,
                    place=None,
                    line=None,
                    column=None,
                    parameters=(),
                    variables=(),
                    cursors=(),
                ),
            ),
        ),
    )
    assert not ends_request(ord("W"), b"\x03")


@pytest.mark.parametrize(
    ("kind", "body"),
    [
        (ord("W"), b"\x04"),
        (ord("W"), b"\x00\x02" + u32(0)),
        (ord("W"), b"\x00\x01" + u32(1) + b"\x01\x03"),
        (ord("V"), b"\x04"),
        (ord("V"), b"\x00" + u32(1)),
    ],
    ids=["no event 4", "no reason 2", "no kind 3", "no Debugged 4", "an ID cut short"],
)
def test_a_malformed_debugger_message_fails_the_connection(
    kind: int, body: bytes
) -> None:
    """Verifies: [PROTOCOL Debugged 'V'] a kind, reason or event of no code, malformed.

    SQLCODE -919, SQLSTATE 08006, as of any frame that cannot be read.
    """
    with pytest.raises(OperationalError) as failure:
        decode(kind, body)
    assert (failure.value.sqlcode, failure.value.sqlstate) == (-919, "08006")
