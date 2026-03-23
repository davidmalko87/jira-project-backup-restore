# backup.py — Jira project backup manager
# Author: David Malko

"""BackupManager orchestrates full backup of Jira project(s).

Collects: project metadata, components, versions, roles, issues
(with changelog), worklogs, attachments, and agile board config.
"""

import logging
import os
from datetime import datetime

from jira_tool.api_client import JiraApiError, JiraClient
from jira_tool.config import JiraConfig
from jira_tool.utils import save_json, sanitize_filename, utc_now_iso

logger = logging.getLogger("jira_tool")


class BackupManager:
    """Orchestrates backup of one or more Jira projects."""

    def __init__(self, client: JiraClient, config: JiraConfig) -> None:
        self.client = client
        self.config = config

    def backup_project(self, project_key: str) -> str:
        """Run full backup for a single project.

        Args:
            project_key: Jira project key (e.g. "DEV", "OPS").

        Returns:
            Path to the backup directory.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = os.path.join(
            self.config.backup_root,
            f"{project_key}_{timestamp}",
        )
        os.makedirs(out_dir, exist_ok=True)

        logger.info("=" * 55)
        logger.info("  Backup: %s", project_key)
        logger.info("  Source: %s", self.config.jira_url)
        logger.info("  Output: %s", out_dir)
        logger.info("=" * 55)

        self._backup_metadata(project_key, out_dir)
        issues = self._backup_issues(project_key, out_dir)

        if issues:
            if self.config.include_worklogs:
                self._backup_worklogs(issues, out_dir)
            if self.config.include_attachments:
                self._backup_attachments(issues, out_dir)

        self._backup_boards(project_key, out_dir)
        self._write_manifest(out_dir, project_key)

        logger.info("[OK] Backup complete -> %s", out_dir)
        return out_dir

    def backup_projects(self, project_keys: list[str]) -> list[str]:
        """Backup multiple projects sequentially.

        Args:
            project_keys: List of project keys to backup.

        Returns:
            List of backup directory paths.
        """
        results: list[str] = []
        for i, key in enumerate(project_keys, 1):
            logger.info(
                "\n>>> Project %d/%d: %s",
                i, len(project_keys), key,
            )
            try:
                path = self.backup_project(key)
                results.append(path)
            except JiraApiError as exc:
                logger.error(
                    "Backup failed for %s: %s", key, exc,
                )
        return results

    # ------------------------------------------------------------------
    # Internal backup steps
    # ------------------------------------------------------------------

    def _backup_metadata(
        self, project_key: str, out_dir: str,
    ) -> None:
        """Fetch project config, components, versions, roles."""
        logger.info("[+] Project metadata...")

        meta = self.client.get(f"/rest/api/3/project/{project_key}")
        save_json(meta, os.path.join(out_dir, "project_meta.json"))
        logger.info("    Saved project_meta.json")

        components = self.client.get(
            f"/rest/api/3/project/{project_key}/components",
        )
        save_json(components, os.path.join(out_dir, "components.json"))
        logger.info("    Saved components.json (%d)", len(components))

        versions = self.client.get(
            f"/rest/api/3/project/{project_key}/versions",
        )
        save_json(versions, os.path.join(out_dir, "versions.json"))
        logger.info("    Saved versions.json (%d)", len(versions))

        roles = self.client.get(
            f"/rest/api/3/project/{project_key}/role",
        )
        save_json(roles, os.path.join(out_dir, "roles.json"))
        logger.info("    Saved roles.json")

    def _backup_issues(
        self, project_key: str, out_dir: str,
    ) -> list[dict]:
        """Paginated fetch of all issues with all fields + changelog."""
        logger.info("[+] Fetching issues...")

        search_body: dict = {
            "jql": f"project = {project_key} ORDER BY created ASC",
            "fields": ["*all"],
        }
        if self.config.include_changelog:
            search_body["expand"] = "changelog"

        all_issues: list[dict] = []
        start = 0

        while True:
            page_body = {
                **search_body,
                "startAt": start,
                "maxResults": self.config.page_size,
            }
            data = self.client.post(
                "/rest/api/3/search/jql", page_body,
            )
            batch = data.get("issues", [])
            total = data.get("total", 0)
            all_issues.extend(batch)

            logger.info(
                "    Issues: %d / %d", len(all_issues), total,
            )

            if start + self.config.page_size >= total or not batch:
                break
            start += self.config.page_size

        save_json(all_issues, os.path.join(out_dir, "issues.json"))
        logger.info("[+] Total issues fetched: %d", len(all_issues))
        return all_issues

    def _backup_worklogs(
        self, issues: list[dict], out_dir: str,
    ) -> None:
        """Fetch worklogs for each issue."""
        logger.info("[+] Fetching worklogs...")

        worklog_dir = os.path.join(out_dir, "worklogs")
        os.makedirs(worklog_dir, exist_ok=True)

        all_worklogs: dict[str, list] = {}

        for issue in issues:
            key = issue["key"]
            try:
                data = self.client.get(
                    f"/rest/api/3/issue/{key}/worklog",
                )
                logs = data.get("worklogs", [])
                if logs:
                    all_worklogs[key] = logs
            except JiraApiError as exc:
                logger.warning(
                    "    Worklog fetch failed for %s: %s", key, exc,
                )

        save_json(
            all_worklogs,
            os.path.join(worklog_dir, "worklogs.json"),
        )
        logger.info(
            "    Worklogs saved for %d issues", len(all_worklogs),
        )

    def _backup_attachments(
        self, issues: list[dict], out_dir: str,
    ) -> None:
        """Download attachment files for each issue."""
        logger.info("[+] Downloading attachments...")

        att_dir = os.path.join(out_dir, "attachments")
        total_ok = 0
        total_fail = 0

        for issue in issues:
            key = issue["key"]
            attachments = (
                (issue.get("fields") or {}).get("attachment") or []
            )
            if not attachments:
                continue

            issue_dir = os.path.join(att_dir, key)
            logger.info(
                "    %s: %d file(s)", key, len(attachments),
            )

            for att in attachments:
                att_id = att.get("id", "")
                filename = att.get("filename", "unknown")
                url = att.get("content", "")
                if not url:
                    continue

                safe_name = f"{att_id}_{sanitize_filename(filename)}"
                dest = os.path.join(issue_dir, safe_name)

                # Skip already-downloaded files (resumability)
                if os.path.exists(dest):
                    logger.debug("        Skip (exists): %s", safe_name)
                    continue

                logger.info("        -> %s", safe_name)
                if self.client.download_file(url, dest):
                    total_ok += 1
                else:
                    total_fail += 1
                    logger.error(
                        "        [X] Failed: %s", safe_name,
                    )

        logger.info(
            "[+] Attachments — OK: %d, Failed: %d",
            total_ok, total_fail,
        )

    def _backup_boards(
        self, project_key: str, out_dir: str,
    ) -> None:
        """Best-effort backup of agile boards, configs, and sprints."""
        logger.info("[+] Board config (best-effort)...")

        try:
            data = self.client.get(
                "/rest/agile/1.0/board",
                params={"projectKeyOrId": project_key},
            )
            boards = data.get("values", [])
            save_json(boards, os.path.join(out_dir, "boards.json"))
            logger.info("    Found %d board(s)", len(boards))

            for board in boards:
                bid = board["id"]

                # Board configuration
                try:
                    cfg = self.client.get(
                        f"/rest/agile/1.0/board/{bid}/configuration",
                    )
                    save_json(
                        cfg,
                        os.path.join(out_dir, f"board_{bid}_config.json"),
                    )
                except JiraApiError:
                    logger.debug(
                        "    Board %d config not available", bid,
                    )

                # Sprints
                try:
                    sprints = self.client.paginate(
                        f"/rest/agile/1.0/board/{bid}/sprint",
                        page_size=50,
                    )
                    if sprints:
                        save_json(
                            sprints,
                            os.path.join(
                                out_dir, f"board_{bid}_sprints.json",
                            ),
                        )
                        logger.info(
                            "    Board %d: %d sprint(s)",
                            bid, len(sprints),
                        )
                except JiraApiError:
                    logger.debug(
                        "    Board %d sprints not available", bid,
                    )

        except JiraApiError as exc:
            logger.warning("    Board config skipped: %s", exc)

    def _write_manifest(
        self, out_dir: str, project_key: str,
    ) -> None:
        """Write manifest.json listing all backed-up files."""
        manifest = {
            "project_key": project_key,
            "source_url": self.config.jira_url,
            "created_at": utc_now_iso(),
            "tool_version": "1.0.0",
            "files": [],
        }

        for root, _, files in os.walk(out_dir):
            for fname in files:
                if fname == "manifest.json":
                    continue
                rel = os.path.relpath(
                    os.path.join(root, fname), out_dir,
                )
                manifest["files"].append(rel)

        save_json(manifest, os.path.join(out_dir, "manifest.json"))
        logger.info(
            "[+] Manifest: %d files", len(manifest["files"]),
        )
