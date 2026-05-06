# auth.py — Build authenticated requests.Session for Jira API
# Author: David Malko

"""Session builder supporting API token auth and cookie auth fallback."""

import requests
import urllib3

from jira_tool.config import JiraConfig


def build_session(config: JiraConfig) -> requests.Session:
    """Create an authenticated requests.Session.

    API token auth (recommended for Cloud):
        Uses HTTPBasicAuth with email + token.

    Cookie auth (fallback for SSO/SAML):
        Injects raw Cookie header from browser DevTools.

    Args:
        config: Validated JiraConfig instance.

    Returns:
        Configured requests.Session ready for API calls.
    """
    if not config.verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    session = requests.Session()
    session.verify = config.verify_ssl
    session.headers.update({"Accept": "application/json"})

    if config.api_token and config.email:
        session.auth = (config.email, config.api_token)
    elif config.cookie_header:
        session.headers["Cookie"] = config.cookie_header
    else:
        raise ValueError(
            "No authentication configured. "
            "Set JIRA_API_TOKEN + JIRA_EMAIL or JIRA_COOKIE_HEADER."
        )

    return session
