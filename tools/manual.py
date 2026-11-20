"""The manual's layout, and every document's links (RULES.md D4, R-DOC-7).

turborel.com's documentation site reads `doc/` alone, so each page opens
with its `# Title` and a line holding only `[Contents](README.md)`, each
volume's README.md lists its pages, a link within `doc/` is a relative
`.md` link that resolves, and a link out of `doc/` is a full URL. A
relative link in any other document resolves too. Each check gives its
findings as lines for a person, empty when the rule holds.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

CONTENTS: Final = "[Contents](README.md)"
"""The line after a page's title, which the site replaces by its sidebar."""

BACK: Final = "[The documentation set](../README.md)"
"""The line of a volume's README.md that leads back to the set."""

README: Final = "README.md"
"""Each folder's contents page."""

_LINK: Final = re.compile(r"\]\(([^)\s]+)\)")
_FENCE: Final = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)
_EXTERNAL: Final = re.compile(r"^[a-z][a-z0-9+.-]*:")


def _targets(text: str) -> list[str]:
    """The relative link targets of `text`, outside its code blocks."""
    targets = _LINK.findall(_FENCE.sub("", text))
    return [t for t in targets if not _EXTERNAL.match(t) and not t.startswith("#")]


def links(path: Path, text: str, doc: Path) -> list[str]:
    """A finding for each relative link of `path` that does not resolve.

    Args:
        path: The Markdown file.
        text: Its text.
        doc: The manual's folder, which a link from within may not leave.

    Returns:
        A finding for each link to no file, or out of `doc` from within it.
    """
    findings = []
    inside = path.resolve().is_relative_to(doc.resolve())
    for target in _targets(text):
        resolved = (path.parent / target.split("#")[0]).resolve()
        if not resolved.exists():
            findings.append(f"{path}: the link {target} leads to no file (R-DOC-7)")
        elif inside and not resolved.is_relative_to(doc.resolve()):
            findings.append(
                f"{path}: the link {target} leaves doc/; give a full URL (R-DOC-7)"
            )
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
        findings += links(path, text, doc)
        if path.is_relative_to(doc):
            findings += page_form(path, text, doc)
    for folder in sorted(p for p in doc.iterdir() if p.is_dir()):
        findings += listed(folder)
    return findings
