"""Tests against Turborel's sample frames, `doc/client/05-protocol-frames.tsv`.

The file is copied into `samples/` at Turborel's main commit 1afa44c2,
as RULES.md D15 says, so the tests read what they read at that commit
whatever the machine holds.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest
from tests.codec.samples.expected_replies import REPLIES
from tests.codec.samples.expected_requests import REQUESTS

from turborel._codec.compress import COMPRESSED, decompress
from turborel._codec.frames import HEADER_BYTES, MAX_BODY, decode_header
from turborel._codec.replies import decode
from turborel._session.capabilities import ALL

FILE: Final = Path(__file__).parent / "samples" / "05-protocol-frames.tsv"
FIELDS: Final = 5


@dataclass(frozen=True, slots=True)
class Sample:
    """A line of the file: who sends the frame, its name, needs, bytes, meaning."""

    direction: str
    name: str
    needs: tuple[str, ...]
    frame: bytes
    means: str


def samples() -> list[Sample]:
    """Every sample of the file, in its order."""
    found = []
    for line in FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        fields = line.split("\t")
        assert len(fields) == FIELDS, line
        direction, name, needs, hexed, means = fields
        assert hexed == hexed.upper()
        wanted = () if needs == "-" else tuple(needs.split(","))
        found.append(Sample(direction, name, wanted, bytes.fromhex(hexed), means))
    return found


SAMPLES: Final = samples()
SERVER: Final = [s for s in SAMPLES if s.direction == "server"]
CLIENT: Final = [s for s in SAMPLES if s.direction == "client"]


def held(sample: Sample) -> tuple[int, bytes]:
    """The kind and body of `sample`'s frame, its header checked; inflated if `z`."""
    kind, length = decode_header(sample.frame[:HEADER_BYTES], MAX_BODY)
    body = sample.frame[HEADER_BYTES:]
    assert len(body) == length
    if kind == COMPRESSED:
        assert "compression" in sample.needs
        return decompress(body)
    return kind, body


def test_every_line_is_read_as_the_page_lays_it_out() -> None:
    """Verifies: [PROTOCOL Sample frames] five fields, apart by tabs, names unique.

    A direction of `client` or `server`, needs of capabilities the
    protocol has or `-`, the whole frame its header too, and a meaning;
    each frame's length is its body's.
    """
    assert len(SAMPLES) == 148
    names = [s.name for s in SAMPLES]
    assert len(set(names)) == len(names)
    for s in SAMPLES:
        assert s.direction in {"client", "server"}
        assert set(s.needs) <= set(ALL), s.needs
        assert s.means
        held(s)
    assert {s.name for s in SERVER} == set(REPLIES)
    assert {s.name for s in CLIENT} == set(REQUESTS)


@pytest.mark.parametrize("sample", SERVER, ids=lambda s: s.name)
def test_every_server_frame_decodes_to_what_it_means(sample: Sample) -> None:
    """Verifies: [PROTOCOL Sample frames] every server frame decoded.

    To the reply its meaning says, written by hand from the meaning; the
    same in its form too, a decimal's scale and a zero's sign.
    """
    reply = decode(*held(sample))
    assert reply == REPLIES[sample.name]
    assert repr(reply) == repr(REPLIES[sample.name])


@pytest.mark.parametrize("sample", CLIENT, ids=lambda s: s.name)
def test_every_client_frame_is_encoded_byte_for_byte(sample: Sample) -> None:
    """Verifies: [PROTOCOL Sample frames] every client frame encoded byte for byte.

    A compressed one's zlib stream is the compressor's own, so its header
    and the frame it inflates to are checked (RULES.md D15).
    """
    encoded = REQUESTS[sample.name]()
    if sample.frame[0] != COMPRESSED:
        assert encoded == sample.frame
        return
    kind, body = held(sample)
    assert bytes([kind]) + len(body).to_bytes(4, "little") + body == encoded


@pytest.mark.parametrize(
    "sample", [s for s in SAMPLES if s.frame[0] == COMPRESSED], ids=lambda s: s.name
)
def test_a_compressed_sample_inflates_to_the_frame_it_names(sample: Sample) -> None:
    """Verifies: [PROTOCOL Sample frames] a `z` sample inflated to the frame it names.

    Its meaning names the held frame's kind and length, the next five
    bytes of the `z` body; the rest is one zlib stream of its body.
    """
    body = sample.frame[HEADER_BYTES:]
    kind, length = body[0], int.from_bytes(body[1:5], "little")
    assert f"kind {chr(kind)}, length {length}," in sample.means
    inflated = zlib.decompress(body[5:])
    assert len(inflated) == length
    assert decompress(body) == (kind, inflated)
