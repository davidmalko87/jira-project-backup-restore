# tests/test_api_client.py — HTTP client retry, backoff, and 2xx handling
# Author: David Malko

"""Offline tests for JiraClient using a fake session (no real network).

Covers retry/backoff on transient errors, 429 rate-limit handling, and the
hardened 2xx handling (202 Accepted + non-JSON body must not crash).
"""

import pytest

from jira_tool.api_client import JiraApiError, JiraClient
from jira_tool.config import JiraConfig


class FakeResponse:
    def __init__(self, status_code, body="", json_data=None, headers=None):
        self.status_code = status_code
        self.text = body
        self._json = json_data
        self.headers = headers or {}

    def json(self):
        if self._json is None:
            raise ValueError("No JSON object could be decoded")
        return self._json


class FakeSession:
    """Records calls and returns a queued list of responses."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def request(self, *args, **kwargs):
        self.calls += 1
        return self._responses.pop(0)


def _client(session, max_retries=3):
    cfg = JiraConfig(
        jira_url="https://x.atlassian.net",
        email="e@x.com", api_token="t",
        max_retries=max_retries, api_delay=0, read_timeout=1,
    )
    return JiraClient(session, "https://x.atlassian.net", cfg)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """Make retry/backoff sleeps instant so tests run fast."""
    monkeypatch.setattr("jira_tool.api_client.time.sleep", lambda *_: None)


def test_get_success_json():
    sess = FakeSession([FakeResponse(200, "{}", {"key": "VAL"})])
    assert _client(sess).get("/x") == {"key": "VAL"}


def test_204_returns_empty_dict():
    sess = FakeSession([FakeResponse(204, "")])
    assert _client(sess).get("/x") == {}


def test_202_accepted_is_success():
    """Regression: 202 must be treated as success, not a hard error."""
    sess = FakeSession([FakeResponse(202, "")])
    assert _client(sess).post("/x", {}) == {}


def test_200_with_non_json_body_does_not_crash():
    """Regression: a 2xx with a non-JSON body returns {} instead of raising."""
    sess = FakeSession([FakeResponse(200, "<html>maintenance</html>")])
    assert _client(sess).get("/x") == {}


def test_retries_on_500_then_succeeds():
    sess = FakeSession([
        FakeResponse(500, "err"),
        FakeResponse(503, "err"),
        FakeResponse(200, "{}", {"ok": True}),
    ])
    assert _client(sess).get("/x") == {"ok": True}
    assert sess.calls == 3


def test_non_retryable_error_raises():
    sess = FakeSession([FakeResponse(400, "bad request")])
    with pytest.raises(JiraApiError) as exc:
        _client(sess).get("/x")
    assert exc.value.status_code == 400


def test_429_then_success():
    sess = FakeSession([
        FakeResponse(429, "slow down", headers={"Retry-After": "0"}),
        FakeResponse(200, "{}", {"ok": True}),
    ])
    assert _client(sess).get("/x") == {"ok": True}
    assert sess.calls == 2


def test_exhausts_retries_and_raises():
    sess = FakeSession([FakeResponse(500, "err")] * 3)
    with pytest.raises(JiraApiError):
        _client(sess, max_retries=3).get("/x")
    assert sess.calls == 3
