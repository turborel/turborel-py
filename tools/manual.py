"""The manual's layout, and every document's links (RULES.md D4, R-DOC-7).

turborel.com's documentation site reads `doc/`, so each page opens with
its `# Title` and a line holding only `[Contents](README.md)`, each
volume's README.md lists its pages, `user/01-installing.md` keeps its
name, and `doc/` holds no images. A relative link resolves, in `doc/`
and in every other document: one from `doc/` to another file of the
repository is relative too, as the site points it at GitHub at the same
tag. Each check gives its findings as lines for a person, empty when the
rule holds.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

CONTENTS: Final = "[Contents](README.md)"
"""The line after a page's title, which the site replaces by its sidebar."""

BACK: Final = "[Turborel Python Driver Documentation](../README.md)"
"""The line of a volume's README.md that leads back to the set."""

README: Final = "README.md"
"""Each folder's contents page."""

_LINK: Final = re.compile(r"\]\(([^)\s]+)\)")
_FENCE: Final = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
_EXTERNAL: Final = re.compile(r"^[a-z][a-z0-9+.-]*:")
_IMAGE: Final = re.compile(r"!\[[^\]]*\]\(|<img\b", re.IGNORECASE)
_IMAGE_SUFFIXES: Final = frozenset({".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"})

INSTALLING: Final = "user/01-installing.md"
"""The chapter the site links as the driver's installing page."""


def _targets(text: str) -> list[str]:
    """The relative link targets of `text`, outside its code blocks."""
    targets = _LINK.findall(_FENCE.sub("", text))
    return [t for t in targets if not _EXTERNAL.match(t) and not t.startswith("#")]


def links(path: Path, text: str) -> list[str]:
    """A finding for each relative link of `path` that does not resolve.

    Args:
        path: The Markdown file.
        text: Its text.

    Returns:
        A finding for each link to no file.
    """
    return [
        f"{path}: the link {target} leads to no file (R-DOC-7)"
        for target in _targets(text)
        if not (path.parent / target.split("#")[0]).exists()
    ]


def images(doc: Path) -> list[str]:
    """R-DOC-7: a finding for each image in `doc`, a file or a Markdown one."""
    findings = [
        f"{path}: the manual holds no images (R-DOC-7)"
        for path in sorted(doc.rglob("*"))
        if path.suffix.lower() in _IMAGE_SUFFIXES
    ]
    findings += [
        f"{path}: the manual holds no images (R-DOC-7)"
        for path in sorted(doc.rglob("*.md"))
        if _IMAGE.search(path.read_text(encoding="utf-8"))
    ]
    if not (doc / INSTALLING).exists():
        findings.append(f"{doc / INSTALLING}: the chapter keeps its name (R-DOC-7)")
    return findings


def page_form(path: Path, text: str, doc: Path) -> list[str]:
    """R-DOC-7: the finding if a page of the manual is not in its form.

    A page opens with `# Title`, then a blank line, then `CONTENTS`; a
    volume's README.md opens with its title and has the line `BACK`; the
    set's own README.md, `doc`'s, opens with its title.
    """
    lines = text.splitlines()
    titled = bool(lines) and lines[0].startswith("# ")
    if path.name != README:
        formed = titled and lines[1:3] == ["", CONTENTS]
    elif path.parent.resolve() == doc.resolve():
        formed = titled
    else:
        formed = titled and BACK in lines
    if formed:
        return []
    return [f"{path}: a page opens with its # Title, then {CONTENTS} (R-DOC-7)"]


def listed(folder: Path) -> list[str]:
    """R-DOC-7: a finding for each page of a volume its README.md leaves out."""
    readme = folder / README
    if not readme.exists():
        return [f"{folder}: a volume has a {README} (R-DOC-7)"]
    targets = set(_targets(readme.read_text(encoding="utf-8")))
    return [
        f"{readme}: it does not list {page.name} (R-DOC-7)"
        for page in sorted(folder.glob("*.md"))
        if page.name != README and page.name not in targets
    ]


def check(root: Path) -> list[str]:
    """Every finding of the manual's form and of every document's links.

    Args:
        root: The repository's root.

    Returns:
        Every finding.
    """
    doc = root / "doc"
    findings: list[str] = []
    documents = sorted(root.glob("*.md")) + sorted(doc.rglob("*.md"))
    for path in documents:
        text = path.read_text(encoding="utf-8")
        findings += links(path, text)
        if path.is_relative_to(doc):
            findings += page_form(path, text, doc)
    for folder in sorted(p for p in doc.iterdir() if p.is_dir()):
        findings += listed(folder)
    return findings + images(doc)
