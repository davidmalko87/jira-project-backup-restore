# adf.py — Atlassian Document Format helpers
# Author: David Malko

"""Helpers for converting text to Atlassian Document Format (ADF).

Jira Cloud API v3 requires ADF for description and comment bodies.
"""


def text_to_adf(text: str) -> dict:
    """Wrap plain text in ADF structure.

    Splits text by newlines into separate paragraphs for better
    readability than a single giant paragraph.

    Args:
        text: Plain text content.

    Returns:
        ADF document dict compatible with Jira Cloud API v3.
    """
    if not text:
        return {"version": 1, "type": "doc", "content": []}

    paragraphs = []
    for line in str(text).split("\n"):
        if line.strip():
            paragraphs.append({
                "type": "paragraph",
                "content": [{"type": "text", "text": line}],
            })
        else:
            # Empty line becomes empty paragraph (visual spacing)
            paragraphs.append({"type": "paragraph", "content": []})

    return {"version": 1, "type": "doc", "content": paragraphs}
