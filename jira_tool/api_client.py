# api_client.py — HTTP client for Jira REST API with retry and rate limiting
# Author: David Malko

"""JiraClient wraps requests.Session with exponential backoff,
429 rate-limit handling, streaming downloads, and auto-pagination.
"""

import logging
import os
import time

import requests
from requests.exceptions import (
    ChunkedEncodingError,
    ConnectionError,
    ReadTimeout,
)

from jira_tool.config import JiraConfig

logger = logging.getLogger("jira_tool")

# Transient HTTP status codes worth retrying
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class JiraApiError(Exception):
    """Raised when Jira API returns a non-retryable error."""

    def __init__(self, status_code: int, url: str, body: str) -> None:
        self.status_code = status_code
        self.url = url
        self.body = body
        super().__init__(
            f"HTTP {status_code} from {url}: {body[:300]}"
        )


class JiraClient:
    """HTTP client for Jira REST API with retry, rate-limit, and pagination."""

    def __init__(
        self,
        session: requests.Session,
        base_url: str,
        config: JiraConfig,
    ) -> None:
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.config = config

    # ------------------------------------------------------------------
    # Core HTTP methods
    # ------------------------------------------------------------------

    def get(self, path: str, params: dict | None = None) -> dict:
        """GET with retry and rate-limit handling.

        Args:
            path: API path (e.g. /rest/api/3/project/KEY).
            params: Query parameters.

        Returns:
            Parsed JSON response.

        Raises:
            JiraApiError: On non-retryable HTTP error.
        """
        return self._request("GET", path, params=params)

    def post(
        self,
        path: str,
        body: dict | None = None,
    ) -> dict:
        """POST with retry and rate-limit handling.

        Args:
            path: API path.
            body: JSON request body.

        Returns:
            Parsed JSON response (or empty dict for 204).

        Raises:
            JiraApiError: On non-retryable HTTP error.
        """
        return self._request("POST", path, json_body=body)

    def upload_file(
        self,
        path: str,
        file_path: str,
        filename: str | None = None,
    ) -> dict:
        """Upload a file as multipart form data.

        Requires X-Atlassian-Token: no-check header for Jira attachments.

        Args:
            path: API path (e.g. /rest/api/3/issue/KEY-1/attachments).
            file_path: Local path to file.
            filename: Override filename sent to Jira (default: basename).

        Returns:
            Parsed JSON response.
        """
        if filename is None:
            filename = os.path.basename(file_path)

        url = f"{self.base_url}{path}"
        headers = {"X-Atlassian-Token": "no-check"}

        for attempt in range(1, self.config.max_retries + 1):
            try:
                with open(file_path, "rb") as f:
                    resp = self.session.post(
                        url,
                        headers=headers,
                        files={"file": (filename, f)},
                    )

                time.sleep(self.config.api_delay)

                if resp.status_code in (200, 201, 202):
                    logger.debug(
                        "UPLOAD %s -> %d (%s)",
                        url, resp.status_code, filename,
                    )
                    try:
                        return resp.json()
                    except ValueError:
                        return {}

                if resp.status_code == 429:
                    self._handle_rate_limit(resp, attempt)
                    continue

                if resp.status_code in RETRYABLE_STATUS:
                    wait = min(2 ** attempt, 30)
                    logger.warning(
                        "Upload retry %d/%d for %s: HTTP %d",
                        attempt, self.config.max_retries,
                        filename, resp.status_code,
                    )
                    time.sleep(wait)
                    continue

                raise JiraApiError(
                    resp.status_code, url, resp.text
                )

            except (ConnectionError, ReadTimeout) as exc:
                logger.warning(
                    "Upload connection error %d/%d for %s: %s",
                    attempt, self.config.max_retries, filename, exc,
                )
                if attempt == self.config.max_retries:
                    raise
                time.sleep(min(2 ** attempt, 30))

        raise JiraApiError(0, url, "Max retries exceeded for upload")

    def download_file(self, url: str, dest_path: str) -> bool:
        """Stream a file to disk with retries.

        Args:
            url: Full URL or relative path to download.
            dest_path: Local destination path.

        Returns:
            True on success, False after all retries exhausted.
        """
        if url.startswith("/"):
            url = self.base_url + url

        for attempt in range(1, self.config.max_retries + 1):
            try:
                resp = self.session.get(
                    url, stream=True, timeout=(10, 600),
                )

                if resp.status_code == 429:
                    self._handle_rate_limit(resp, attempt)
                    continue

                if resp.status_code != 200:
                    logger.warning(
                        "Download HTTP %d attempt %d/%d: %s",
                        resp.status_code, attempt,
                        self.config.max_retries, url,
                    )
                    if attempt < self.config.max_retries:
                        time.sleep(min(2 ** attempt, 30))
                    continue

                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                with open(dest_path, "wb") as f:
                    for chunk in resp.iter_content(
                        chunk_size=self.config.chunk_size
                    ):
                        if chunk:
                            f.write(chunk)

                logger.debug("Downloaded: %s", dest_path)
                return True

            except (
                ChunkedEncodingError, ConnectionError, ReadTimeout,
            ) as exc:
                logger.warning(
                    "Download error %d/%d: %s — %s",
                    attempt, self.config.max_retries, url, exc,
                )
            except OSError as exc:
                logger.error("Filesystem error downloading %s: %s", url, exc)
                break

            # Clean up partial file before retry
            if os.path.exists(dest_path):
                try:
                    os.remove(dest_path)
                except OSError:
                    pass

        return False

    def paginate(
        self,
        path: str,
        params: dict | None = None,
        result_key: str = "values",
        page_size: int | None = None,
    ) -> list[dict]:
        """Auto-paginate through a Jira list endpoint.

        Handles both styles of Jira pagination:
        - startAt/maxResults/total (search, components, etc.)
        - startAt/maxResults/isLast (agile endpoints)

        Args:
            path: API path.
            params: Base query parameters (startAt/maxResults added automatically).
            result_key: JSON key containing the list items.
            page_size: Override page size for this request.

        Returns:
            Combined list of all items across pages.
        """
        all_items: list[dict] = []
        start = 0
        size = page_size or self.config.page_size
        base_params = dict(params or {})

        while True:
            page_params = {
                **base_params,
                "startAt": start,
                "maxResults": size,
            }
            data = self.get(path, params=page_params)

            items = data.get(result_key) or data.get("issues") or []
            all_items.extend(items)

            total = data.get("total")
            is_last = data.get("isLast", None)

            if is_last is True:
                break
            if total is not None and start + size >= total:
                break
            if not items:
                break

            start += size

        return all_items

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> dict:
        """Execute HTTP request with retry and rate-limit handling."""
        url = f"{self.base_url}{path}"

        for attempt in range(1, self.config.max_retries + 1):
            try:
                resp = self.session.request(
                    method, url,
                    params=params,
                    json=json_body,
                    headers=(
                        {"Content-Type": "application/json"}
                        if json_body is not None else None
                    ),
                    timeout=self.config.read_timeout or None,
                )

                time.sleep(self.config.api_delay)

                logger.debug(
                    "%s %s -> %d", method, path, resp.status_code,
                )

                # 202 Accepted is a success (some endpoints return it for
                # async work). A 2xx with an empty or non-JSON body must not
                # crash — return an empty dict instead of raising JSONDecodeError.
                if resp.status_code in (200, 201, 202, 204):
                    if resp.status_code == 204 or not resp.text:
                        return {}
                    try:
                        return resp.json()
                    except ValueError:
                        logger.debug(
                            "%s %s -> %d with non-JSON body (%d bytes)",
                            method, path, resp.status_code, len(resp.text),
                        )
                        return {}

                if resp.status_code == 429:
                    self._handle_rate_limit(resp, attempt)
                    continue

                if resp.status_code in RETRYABLE_STATUS:
                    wait = min(2 ** attempt, 30)
                    logger.warning(
                        "Retry %d/%d: %s %s -> %d",
                        attempt, self.config.max_retries,
                        method, path, resp.status_code,
                    )
                    time.sleep(wait)
                    continue

                # Non-retryable error
                raise JiraApiError(
                    resp.status_code, url, resp.text,
                )

            except (ConnectionError, ReadTimeout) as exc:
                logger.warning(
                    "Connection error %d/%d: %s %s — %s",
                    attempt, self.config.max_retries, method, path, exc,
                )
                if attempt == self.config.max_retries:
                    raise
                time.sleep(min(2 ** attempt, 30))

        raise JiraApiError(0, url, "Max retries exceeded")

    def _handle_rate_limit(
        self,
        resp: requests.Response,
        attempt: int,
    ) -> None:
        """Sleep according to Retry-After header or exponential backoff."""
        retry_after = resp.headers.get("Retry-After")
        if retry_after:
            try:
                wait = int(retry_after)
            except ValueError:
                wait = min(2 ** attempt, 60)
        else:
            wait = min(2 ** attempt, 60)

        logger.warning(
            "Rate limited (429). Waiting %ds before retry %d/%d.",
            wait, attempt, self.config.max_retries,
        )
        time.sleep(wait)
