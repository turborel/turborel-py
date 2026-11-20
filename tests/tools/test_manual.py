"""Tests of the manual's form and the documents' links, as `tools.manual` checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tools.manual import BACK, CONTENTS, check, images, links, listed, page_form

if TYPE_CHECKING:
    from pathlib import Path


def write(path: Path, text: str) -> Path:
    """Write `text` to `path`, its folders made."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_a_page_opens_with_its_title_then_contents(tmp_path: Path) -> None:
    """Verifies: [TOOL] R-DOC-7 a page's `# Title`, then `[Contents](README.md)`.

    A volume's README.md leads back to the set; the set's own needs its
    title alone.
    """
    doc = tmp_path / "doc"
    page = doc / "user" / "01-a.md"
    assert page_form(page, f"# A\n\n{CONTENTS}\n\nText.\n", doc) == []
    assert page_form(page, "# A\n\nText.\n", doc) != []
    assert page_form(page, f"A\n\n{CONTENTS}\n", doc) != []
    volume = doc / "user" / "README.md"
    assert page_form(volume, f"# Volume I\n\n{BACK}\n", doc) == []
    assert page_form(volume, "# Volume I\n", doc) != []
    assert page_form(doc / "README.md", "# The Set\n", doc) == []


def test_every_page_of_a_volume_is_listed(tmp_path: Path) -> None:
    """Verifies: [TOOL] R-DOC-7 each volume's README.md lists its pages."""
    folder = tmp_path / "user"
    write(folder / "01-a.md", "# A\n")
    write(folder / "02-b.md", "# B\n")
    write(folder / "README.md", "- [A](01-a.md)\n")
    assert listed(folder) == [
        f"{folder / 'README.md'}: it does not list 02-b.md (R-DOC-7)"
    ]
    assert listed(tmp_path / "none") != []


def test_links_resolve(tmp_path: Path) -> None:
    """Verifies: [TOOL] R-DOC-7 relative links resolve, in doc/ and out of it.

    A link from doc/ to another file of the repository is relative; a
    full URL and an anchor are not followed; a link in a code block is
    not a link.
    """
    write(tmp_path / "RULES.md", "# Rules\n")
    page = write(tmp_path / "doc" / "user" / "01-a.md", "")
    write(tmp_path / "doc" / "README.md", "# Set\n")
    good = "[Set](../README.md) [Web](https://example.org/x.md) [Here](#a)\n"
    assert links(page, good + "[Rules](../../RULES.md)\n") == []
    assert len(links(page, "[Gone](02-b.md)\n")) == 1
    assert links(page, "```\n[Gone](02-b.md)\n```\n") == []
    assert links(tmp_path / "README.md", "[Rules](RULES.md)\n") == []


def test_the_manual_holds_no_images(tmp_path: Path) -> None:
    """Verifies: [TOOL] R-DOC-7 no image in doc/, and the installing chapter kept."""
    doc = tmp_path / "doc"
    write(doc / "user" / "01-installing.md", "# Installing\n")
    assert images(doc) == []
    write(doc / "logo.svg", "<svg/>")
    write(doc / "user" / "02-b.md", "![Logo](../logo.svg)\n")
    assert len(images(doc)) == 2
    assert len(images(tmp_path / "none")) == 1


def test_every_document_is_checked(tmp_path: Path) -> None:
    """Verifies: [TOOL] R-DOC-7 the root's documents and every page of doc/."""
    write(tmp_path / "README.md", "[Manual](doc/README.md) [Gone](NOPE.md)\n")
    write(tmp_path / "doc" / "README.md", "# Set\n\n- [I](user/README.md)\n")
    write(
        tmp_path / "doc" / "user" / "README.md",
        f"# I\n\n{BACK}\n\n- [A](01-a.md)\n- [I](01-installing.md)\n",
    )
    write(tmp_path / "doc" / "user" / "01-a.md", "# A\n\nNo contents line.\n")
    write(tmp_path / "doc" / "user" / "01-installing.md", f"# I\n\n{CONTENTS}\n")
    findings = check(tmp_path)
    assert len(findings) == 2
    assert "NOPE.md" in findings[0]
    assert "01-a.md" in findings[1]
