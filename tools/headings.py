"""The headings a test may cite, as turborel's documents give them.

Taken from turborel's doc/client/05-protocol.md (`PROTOCOL`), and from
02-library.md and 02-library-connections.md (`CLIENT`), at main's commit
e4f08f77. A heading the documents rename or add is changed here in the
same commit as the code that follows it (RULES.md D6, R-TRACE-2). Each
document's title, its first heading, is one of its headings too.
"""

from __future__ import annotations

from typing import Final

PROTOCOL: Final = frozenset(
    {
        "The Native Protocol",
        "Frames",
        "Compressed frames",
        "Values and fields",
        "Data types",
        "Values",
        "Composite fields",
        "The tail",
        "Opening a connection",
        "Mechanisms",
        "Capabilities",
        "Requests",
        "Hello 'H'",
        "Answer 'A'",
        "Query 'Q'",
        "Prepare 'P'",
        "Execute 'E'",
        "Fetch 'F'",
        "Close 'C'",
        "Deallocate 'D'",
        "Lob 'L'",
        "Cancel 'Z'",
        "Terminate 'X'",
        "Describe 'Y'",
        "Ping 'G'",
        "Reset 'W'",
        "ChangeUser 'U'",
        "CopyIn 'I'",
        "CopyData 'J'",
        "CopyEnd 'N'",
        "Replies",
        "Challenge 'C'",
        "Ready 'R'",
        "Prepared 'P'",
        "Description 'D'",
        "Rows 'B'",
        "Suspended 'S'",
        "Complete 'K'",
        "Error 'E'",
        "Notice 'N'",
        "Status 'T'",
        "Pong 'G'",
        "Conversations",
        "Errors and notices",
        "A worked example",
    }
)
"""The headings of doc/client/05-protocol.md."""

CLIENT: Final = frozenset(
    {
        # 02-library.md
        "The Client Library",
        "Connecting",
        "Timeouts",
        "Running statements",
        "Prepared statements",
        "Large objects",
        "XML values",
        "UUIDs",
        "Importing",
        "What a connection asks for",
        "What the server tells",
        "Controlling the session",
        "Copying and exporting",
        "The SQL-agent",
        # 02-library-connections.md
        "Settings, Pipelines and Pools",
        "Connecting by settings",
        "Where settings come from",
        "The connection URI",
        "The service file",
        "The password file",
        "Several servers",
        "TLS by mode",
        "Pipelines",
        "Pools",
        "The SCRAM key cache",
    }
)
"""The headings of doc/client/02-library.md and 02-library-connections.md."""

DOCUMENTS: Final = {"PROTOCOL": PROTOCOL, "CLIENT": CLIENT}
"""Each document's tag in a citation, and its headings."""
