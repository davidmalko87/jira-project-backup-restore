# tests/test_config.py — Configuration validation
# Author: David Malko

"""Offline tests for JiraConfig.validate."""

from jira_tool.config import JiraConfig


def test_valid_api_token_config():
    cfg = JiraConfig(
        jira_url="https://x.atlassian.net",
        email="e@x.com",
        api_token="tok",
    )
    assert cfg.validate() == []


def test_missing_url():
    cfg = JiraConfig(email="e@x.com", api_token="tok")
    errors = cfg.validate()
    assert any("JIRA_URL" in e for e in errors)


def test_trailing_slash_stripped():
    cfg = JiraConfig(
        jira_url="https://x.atlassian.net/",
        email="e@x.com",
        api_token="tok",
    )
    cfg.validate()
    assert cfg.jira_url == "https://x.atlassian.net"


def test_no_auth_method():
    cfg = JiraConfig(jira_url="https://x.atlassian.net")
    errors = cfg.validate()
    assert any("API_TOKEN" in e or "COOKIE" in e for e in errors)


def test_api_token_requires_email():
    cfg = JiraConfig(jira_url="https://x.atlassian.net", api_token="tok")
    errors = cfg.validate()
    assert any("EMAIL" in e for e in errors)


def test_cookie_auth_without_email_ok():
    cfg = JiraConfig(
        jira_url="https://x.atlassian.net",
        cookie_header="JSESSIONID=abc",
    )
    assert cfg.validate() == []


def test_page_size_bounds():
    too_big = JiraConfig(
        jira_url="https://x.atlassian.net",
        email="e@x.com", api_token="t", page_size=500,
    )
    assert any("PAGE_SIZE" in e for e in too_big.validate())

    too_small = JiraConfig(
        jira_url="https://x.atlassian.net",
        email="e@x.com", api_token="t", page_size=0,
    )
    assert any("PAGE_SIZE" in e for e in too_small.validate())
