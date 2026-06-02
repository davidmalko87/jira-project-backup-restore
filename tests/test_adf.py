# tests/test_adf.py — ADF conversion and flattening
# Author: David Malko

"""Offline tests for ADF helpers: text->ADF, ADF->text, and attribution."""

from jira_tool.adf import text_to_adf
from jira_tool.restore import _adf_with_attribution, _extract_text_from_adf


def test_text_to_adf_basic():
    adf = text_to_adf("hello")
    assert adf["type"] == "doc"
    assert adf["version"] == 1
    assert adf["content"][0]["content"][0]["text"] == "hello"


def test_text_to_adf_empty():
    adf = text_to_adf("")
    assert adf == {"version": 1, "type": "doc", "content": []}


def test_text_to_adf_multiline_makes_paragraphs():
    adf = text_to_adf("line1\nline2")
    paras = [c for c in adf["content"] if c["content"]]
    assert len(paras) == 2


def test_extract_text_roundtrip():
    adf = text_to_adf("first\nsecond")
    text = _extract_text_from_adf(adf)
    assert "first" in text and "second" in text


def test_extract_text_from_nested_adf():
    adf = {
        "type": "doc",
        "version": 1,
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "A"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "B"}]},
        ],
    }
    assert _extract_text_from_adf(adf) == "A\nB"


def test_adf_with_attribution_preserves_adf_body():
    """Regression: an ADF dict body must NOT be stringified into the text."""
    body = text_to_adf("real comment text")
    result = _adf_with_attribution("[Originally by X]", body)

    flat = _extract_text_from_adf(result)
    assert "[Originally by X]" in flat
    assert "real comment text" in flat
    # The bug produced "{'type': 'doc'...}" in the text — ensure it's gone.
    assert "'type'" not in flat
    assert "{" not in flat


def test_adf_with_attribution_plain_text_body():
    result = _adf_with_attribution("[by X]", "plain string body")
    flat = _extract_text_from_adf(result)
    assert "[by X]" in flat
    assert "plain string body" in flat


def test_adf_with_attribution_empty_body():
    result = _adf_with_attribution("[by X]", None)
    flat = _extract_text_from_adf(result)
    assert flat.strip() == "[by X]"
    # Attribution is always the first paragraph.
    assert result["content"][0]["content"][0]["text"] == "[by X]"
