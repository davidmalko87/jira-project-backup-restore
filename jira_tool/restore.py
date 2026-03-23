# restore.py — Jira project restore manager
# Author: David Malko

"""RestoreManager orchestrates 5-phase restore of a Jira project backup
into Jira Cloud via REST API v3.

Phases:
  1. Create issues (epics -> regular -> subtasks)
  2. Restore issue links
  3. Restore comments (with author attribution)
  4. Restore worklogs (with author attribution)
  5. Upload attachments

Each phase is resumable — progress is tracked in ProgressTracker.

Known Jira Cloud API limitations:
  - Cannot set created/updated timestamps
  - Cannot set original author on comments/worklogs
  - Issue keys are reassigned by Cloud (tracked in key_mapping.json)
  - Status resets to project default on create
  - Changelog/history cannot be imported
"""

import logging
import os
from datetime import datetime, timezone

from jira_tool.adf import text_to_adf
from jira_tool.api_client import JiraApiError, JiraClient
from jira_tool.config import JiraConfig
from jira_tool.progress import ProgressTracker
from jira_tool.utils import load_json

logger = logging.getLogger("jira_tool")


class RestoreManager:
    """Orchestrates restore of a backup into Jira Cloud."""

    def __init__(
        self,
        client: JiraClient,
        config: JiraConfig,
        progress: ProgressTracker,
    ) -> None:
        self.client = client
        self.config = config
        self.progress = progress

    def restore_project(
        self,
        backup_dir: str,
        target_project_key: str,
        dry_run: bool = False,
        phases: dict[str, bool] | None = None,
    ) -> None:
        """Run the full restore pipeline.

        Args:
            backup_dir: Path to backup directory.
            target_project_key: Jira Cloud project key to restore into.
            dry_run: If True, log actions without making API calls.
            phases: Override which phases to run. Keys: "issues",
                "links", "comments", "worklogs", "attachments".
                Default: all enabled.
        """
        run = phases or {
            "issues": True,
            "links": True,
            "comments": True,
            "worklogs": True,
            "attachments": True,
        }

        logger.info("=" * 55)
        logger.info("  Restore to: %s", target_project_key)
        logger.info("  Jira Cloud: %s", self.config.jira_url)
        logger.info("  Backup dir: %s", backup_dir)
        logger.info("  Dry run:    %s", dry_run)
        logger.info("=" * 55)

        if run.get("issues"):
            self._phase_create_issues(
                backup_dir, target_project_key, dry_run,
            )

        if run.get("links"):
            self._phase_restore_links(backup_dir, dry_run)

        if run.get("comments"):
            self._phase_restore_comments(backup_dir, dry_run)

        if run.get("worklogs"):
            self._phase_restore_worklogs(backup_dir, dry_run)

        if run.get("attachments"):
            self._phase_restore_attachments(backup_dir, dry_run)

        logger.info("\n[OK] Restore complete.")

    # ------------------------------------------------------------------
    # Phase 1 — Create Issues
    # ------------------------------------------------------------------

    def _phase_create_issues(
        self,
        backup_dir: str,
        target_key: str,
        dry_run: bool,
    ) -> None:
        """Create issues: epics first, regular issues, subtasks last."""
        if self.progress.is_phase_complete("issues"):
            logger.info("[PHASE 1] Already complete — skipping.")
            return

        logger.info("\n[PHASE 1] Creating issues...")

        issues_path = os.path.join(backup_dir, "issues.json")
        if not os.path.exists(issues_path):
            logger.warning("  issues.json not found — skipping.")
            return

        issues = load_json(issues_path)
        ok = skip = fail = 0

        def _sort_key(issue: dict) -> int:
            """Sort: 0=Epic, 1=Regular, 2=Sub-task."""
            itype = (
                (issue.get("fields") or {})
                .get("issuetype", {})
                .get("name", "")
            )
            if itype == "Epic":
                return 0
            if itype in ("Sub-task", "Subtask"):
                return 2
            return 1

        # Two-pass: non-subtasks first, then subtasks
        # Why: subtasks need parent key mapping to exist
        for pass_num, pass_label in enumerate(
            ["non-subtask", "subtask"]
        ):
            for issue in sorted(issues, key=_sort_key):
                orig_key = issue["key"]
                fields = issue.get("fields", {}) or {}
                itype_name = (
                    (fields.get("issuetype") or {}).get("name", "")
                )
                is_subtask = itype_name in ("Sub-task", "Subtask")

                if pass_num == 0 and is_subtask:
                    continue
                if pass_num == 1 and not is_subtask:
                    continue

                # Skip already-created issues
                if self.progress.is_issue_created(orig_key):
                    skip += 1
                    logger.debug(
                        "  Skip (exists): %s -> %s",
                        orig_key,
                        self.progress.get_cloud_key(orig_key),
                    )
                    continue

                payload = self._build_issue_payload(
                    issue, target_key,
                )

                # Subtask parent linking
                if is_subtask:
                    orig_parent = (
                        (fields.get("parent") or {}).get("key")
                    )
                    if not orig_parent:
                        # Try epic link custom field as fallback
                        epic_field = fields.get("customfield_10008")
                        if isinstance(epic_field, dict):
                            orig_parent = epic_field.get("key")

                    cloud_parent = self.progress.get_cloud_key(
                        orig_parent or "",
                    )
                    if cloud_parent:
                        payload["fields"]["parent"] = {
                            "key": cloud_parent,
                        }

                if dry_run:
                    summary = fields.get("summary", "")[:60]
                    logger.info(
                        "  [DRY] %s — %s", orig_key, summary,
                    )
                    self.progress.map_key(
                        orig_key, f"DRY-{orig_key}",
                    )
                    ok += 1
                    continue

                try:
                    result = self.client.post(
                        "/rest/api/3/issue", payload,
                    )
                    cloud_key = result.get("key", "")
                    self.progress.map_key(orig_key, cloud_key)
                    logger.info(
                        "  Created: %s -> %s", orig_key, cloud_key,
                    )
                    self._post_metadata_comment(
                        cloud_key, orig_key, fields,
                    )
                    ok += 1
                except JiraApiError as exc:
                    # Retry without assignee if user can't be assigned
                    if (
                        exc.status_code == 400
                        and "assignee" in payload.get("fields", {})
                        and "cannot be assigned" in str(exc)
                    ):
                        payload["fields"].pop("assignee")
                        logger.warning(
                            "  Assignee rejected for %s — "
                            "retrying without assignee",
                            orig_key,
                        )
                        try:
                            result = self.client.post(
                                "/rest/api/3/issue", payload,
                            )
                            cloud_key = result.get("key", "")
                            self.progress.map_key(
                                orig_key, cloud_key,
                            )
                            logger.info(
                                "  Created: %s -> %s "
                                "(without assignee)",
                                orig_key, cloud_key,
                            )
                            self._post_metadata_comment(
                                cloud_key, orig_key, fields,
                            )
                            ok += 1
                            continue
                        except JiraApiError as exc2:
                            exc = exc2

                    logger.error(
                        "  Failed %s: %s", orig_key, exc,
                    )
                    fail += 1

        logger.info(
            "  Done — Created: %d, Skipped: %d, Failed: %d",
            ok, skip, fail,
        )

        if fail == 0:
            self.progress.mark_phase_complete("issues")

    def _build_issue_payload(
        self,
        issue: dict,
        target_key: str,
    ) -> dict:
        """Construct Cloud API v3 issue creation payload."""
        fields = issue.get("fields", {}) or {}
        summary = fields.get("summary") or "(no summary)"
        itype = (
            (fields.get("issuetype") or {}).get("name", "Task")
        )
        priority = (fields.get("priority") or {}).get("name")

        # Resolve reporter
        reporter_email = (
            (fields.get("reporter") or {}).get("emailAddress", "")
        )
        reporter_id = self._resolve_user(reporter_email)

        # Resolve assignee
        assignee_email = (
            (fields.get("assignee") or {}).get("emailAddress", "")
        )
        assignee_id = self._resolve_user(assignee_email)

        # Description -> ADF (may already be ADF dict from v3 backup)
        desc_raw = fields.get("description")
        if isinstance(desc_raw, dict) and desc_raw.get("type") == "doc":
            description_adf = desc_raw
        else:
            description_adf = text_to_adf(desc_raw or "")

        payload: dict = {
            "fields": {
                "project": {"key": target_key},
                "summary": summary,
                "issuetype": {"name": itype},
                "description": description_adf,
                "labels": fields.get("labels") or [],
            },
        }

        if priority:
            payload["fields"]["priority"] = {"name": priority}
        if reporter_id:
            payload["fields"]["reporter"] = {"id": reporter_id}
        if assignee_id:
            payload["fields"]["assignee"] = {"id": assignee_id}

        # Components
        components = fields.get("components") or []
        if components:
            payload["fields"]["components"] = [
                {"name": c["name"]}
                for c in components
                if c.get("name")
            ]

        # Fix versions
        fix_versions = fields.get("fixVersions") or []
        if fix_versions:
            payload["fields"]["fixVersions"] = [
                {"name": v["name"]}
                for v in fix_versions
                if v.get("name")
            ]

        return payload

    @staticmethod
    def _build_metadata_text(
        orig_key: str, fields: dict,
    ) -> str:
        """Build a metadata summary from backup fields.

        Includes original key, status, assignee, and other notable
        fields that cannot be set via the API during restore.
        """
        lines = ["--- Backup Metadata ---"]
        lines.append(f"Original Key: {orig_key}")

        # Status
        status_name = (
            (fields.get("status") or {}).get("name")
        )
        if status_name:
            lines.append(f"Status: {status_name}")

        # Resolution
        resolution = (
            (fields.get("resolution") or {}).get("name")
        )
        if resolution:
            lines.append(f"Resolution: {resolution}")

        # Assignee
        assignee = fields.get("assignee") or {}
        assignee_name = assignee.get(
            "displayName",
            assignee.get("emailAddress"),
        )
        if assignee_name:
            lines.append(f"Assignee: {assignee_name}")

        # Reporter
        reporter = fields.get("reporter") or {}
        reporter_name = reporter.get(
            "displayName",
            reporter.get("emailAddress"),
        )
        if reporter_name:
            lines.append(f"Reporter: {reporter_name}")

        # Priority
        priority = (fields.get("priority") or {}).get("name")
        if priority:
            lines.append(f"Priority: {priority}")

        # Created / Updated / Resolved dates
        if fields.get("created"):
            lines.append(f"Created: {fields['created']}")
        if fields.get("updated"):
            lines.append(f"Updated: {fields['updated']}")
        if fields.get("resolutiondate"):
            lines.append(f"Resolved: {fields['resolutiondate']}")

        # Due date
        if fields.get("duedate"):
            lines.append(f"Due Date: {fields['duedate']}")

        # Story points (common custom fields)
        for cf_key in ("story_points", "customfield_10016"):
            sp = fields.get(cf_key)
            if sp is not None:
                lines.append(f"Story Points: {sp}")
                break

        # Sprint
        sprint = fields.get("sprint") or fields.get(
            "customfield_10020",
        )
        if sprint:
            if isinstance(sprint, list):
                sprint_names = [
                    s.get("name", str(s))
                    if isinstance(s, dict) else str(s)
                    for s in sprint
                ]
                lines.append(f"Sprint: {', '.join(sprint_names)}")
            elif isinstance(sprint, dict):
                lines.append(
                    f"Sprint: {sprint.get('name', str(sprint))}",
                )

        # Epic link
        epic_key = None
        epic_field = fields.get("customfield_10008")
        if isinstance(epic_field, dict):
            epic_key = epic_field.get("key")
        elif isinstance(epic_field, str):
            epic_key = epic_field
        # Also check epic name
        epic_name = fields.get("customfield_10011")
        if epic_key:
            lines.append(f"Epic Link: {epic_key}")
        if epic_name and isinstance(epic_name, str):
            lines.append(f"Epic Name: {epic_name}")

        # Time tracking
        tt = fields.get("timetracking") or {}
        if tt.get("originalEstimate"):
            lines.append(
                f"Original Estimate: {tt['originalEstimate']}",
            )
        if tt.get("timeSpent"):
            lines.append(f"Time Spent: {tt['timeSpent']}")

        # Environment
        env = fields.get("environment")
        if env and isinstance(env, str):
            lines.append(f"Environment: {env}")

        lines.append("--- End Metadata ---")
        return "\n".join(lines)

    def _post_metadata_comment(
        self,
        cloud_key: str,
        orig_key: str,
        fields: dict,
    ) -> None:
        """Post a comment with backup metadata to the restored issue."""
        text = self._build_metadata_text(orig_key, fields)
        try:
            self.client.post(
                f"/rest/api/3/issue/{cloud_key}/comment",
                {"body": text_to_adf(text)},
            )
        except JiraApiError as exc:
            logger.warning(
                "  Could not add metadata comment to %s: %s",
                cloud_key, exc,
            )

    def _resolve_user(self, email: str) -> str | None:
        """Look up Cloud accountId by email, with caching."""
        if not email:
            return None

        found, cached_id = self.progress.get_cached_user(email)
        if found:
            return cached_id

        try:
            result = self.client.get(
                "/rest/api/3/user/search",
                params={"query": email},
            )
            # result is a list when successful
            if isinstance(result, list) and result:
                account_id = result[0].get("accountId")
                self.progress.cache_user(email, account_id)
                return account_id
        except JiraApiError:
            pass

        self.progress.cache_user(email, None)
        return None

    # ------------------------------------------------------------------
    # Phase 2 — Issue Links
    # ------------------------------------------------------------------

    def _phase_restore_links(
        self, backup_dir: str, dry_run: bool,
    ) -> None:
        """Restore issue links (outward-only to avoid duplicates)."""
        if self.progress.is_phase_complete("links"):
            logger.info("[PHASE 2] Already complete — skipping.")
            return

        logger.info("\n[PHASE 2] Restoring issue links...")

        issues_path = os.path.join(backup_dir, "issues.json")
        if not os.path.exists(issues_path):
            logger.warning("  issues.json not found — skipping.")
            return

        issues = load_json(issues_path)
        ok = fail = skip = 0

        for issue in issues:
            orig_key = issue["key"]
            links = (
                (issue.get("fields", {}) or {})
                .get("issuelinks") or []
            )

            for link in links:
                # Process outward only — avoids duplicate links
                outward = link.get("outwardIssue")
                if not outward:
                    continue

                link_type = (
                    (link.get("type") or {}).get("name", "Relates")
                )
                orig_target = outward.get("key")
                cloud_source = self.progress.get_cloud_key(orig_key)
                cloud_target = self.progress.get_cloud_key(
                    orig_target or "",
                )

                if not cloud_source or not cloud_target:
                    logger.debug(
                        "  Missing mapping: %s -> %s",
                        orig_key, orig_target,
                    )
                    skip += 1
                    continue

                # Build unique link ID for dedup
                link_id = (
                    f"{cloud_source}_{link_type}_{cloud_target}"
                )
                if self.progress.is_item_done("links", link_id):
                    skip += 1
                    continue

                payload = {
                    "type": {"name": link_type},
                    "inwardIssue": {"key": cloud_source},
                    "outwardIssue": {"key": cloud_target},
                }

                if dry_run:
                    logger.info(
                        "  [DRY] %s -[%s]-> %s",
                        cloud_source, link_type, cloud_target,
                    )
                    ok += 1
                    continue

                try:
                    self.client.post(
                        "/rest/api/3/issueLink", payload,
                    )
                    self.progress.mark_item_done("links", link_id)
                    logger.info(
                        "  Linked: %s -[%s]-> %s",
                        cloud_source, link_type, cloud_target,
                    )
                    ok += 1
                except JiraApiError as exc:
                    logger.error("  Link failed: %s", exc)
                    fail += 1

        logger.info(
            "  Done — Linked: %d, Skipped: %d, Failed: %d",
            ok, skip, fail,
        )

        if fail == 0:
            self.progress.mark_phase_complete("links")

    # ------------------------------------------------------------------
    # Phase 3 — Comments
    # ------------------------------------------------------------------

    def _phase_restore_comments(
        self, backup_dir: str, dry_run: bool,
    ) -> None:
        """Restore comments with author attribution text."""
        if self.progress.is_phase_complete("comments"):
            logger.info("[PHASE 3] Already complete — skipping.")
            return

        logger.info("\n[PHASE 3] Restoring comments...")

        issues_path = os.path.join(backup_dir, "issues.json")
        if not os.path.exists(issues_path):
            logger.warning("  issues.json not found — skipping.")
            return

        issues = load_json(issues_path)
        ok = fail = 0

        for issue in issues:
            orig_key = issue["key"]
            cloud_key = self.progress.get_cloud_key(orig_key)
            if not cloud_key:
                continue

            comments = (
                ((issue.get("fields", {}) or {})
                 .get("comment") or {})
                .get("comments") or []
            )

            for i, comment in enumerate(comments):
                comment_id = f"{orig_key}_comment_{i}"
                if self.progress.is_item_done(
                    "comments", comment_id,
                ):
                    continue

                author = (
                    (comment.get("author") or {})
                    .get("displayName", "Unknown")
                )
                created = comment.get("created", "")[:10]
                body = comment.get("body") or ""

                # Author attribution — Cloud API doesn't allow
                # setting comment author
                attributed = (
                    f"[Originally by {author} on {created}]"
                    f"\n\n{body}"
                )
                payload = {"body": text_to_adf(attributed)}

                if dry_run:
                    logger.info(
                        "  [DRY] Comment on %s by %s",
                        cloud_key, author,
                    )
                    ok += 1
                    continue

                try:
                    self.client.post(
                        f"/rest/api/3/issue/{cloud_key}/comment",
                        payload,
                    )
                    self.progress.mark_item_done(
                        "comments", comment_id,
                    )
                    ok += 1
                except JiraApiError as exc:
                    logger.error(
                        "  Comment failed on %s: %s",
                        cloud_key, exc,
                    )
                    fail += 1

        logger.info(
            "  Done — Comments: %d, Failed: %d", ok, fail,
        )

        if fail == 0:
            self.progress.mark_phase_complete("comments")

    # ------------------------------------------------------------------
    # Phase 4 — Worklogs
    # ------------------------------------------------------------------

    def _phase_restore_worklogs(
        self, backup_dir: str, dry_run: bool,
    ) -> None:
        """Restore worklogs with author attribution text."""
        if self.progress.is_phase_complete("worklogs"):
            logger.info("[PHASE 4] Already complete — skipping.")
            return

        logger.info("\n[PHASE 4] Restoring worklogs...")

        worklogs_path = os.path.join(
            backup_dir, "worklogs", "worklogs.json",
        )
        if not os.path.exists(worklogs_path):
            logger.warning("  worklogs.json not found — skipping.")
            return

        worklogs = load_json(worklogs_path)
        ok = fail = 0

        for orig_key, logs in worklogs.items():
            cloud_key = self.progress.get_cloud_key(orig_key)
            if not cloud_key:
                logger.debug(
                    "  No mapping for %s — skipping worklogs",
                    orig_key,
                )
                continue

            for i, log in enumerate(logs):
                log_id = f"{orig_key}_worklog_{i}"
                if self.progress.is_item_done("worklogs", log_id):
                    continue

                author = (
                    (log.get("author") or {})
                    .get("displayName", "Unknown")
                )
                started = log.get(
                    "started",
                    datetime.now(timezone.utc).isoformat(),
                )
                seconds = log.get("timeSpentSeconds", 0)
                comment = log.get("comment") or ""

                if not seconds:
                    continue

                note = (
                    f"[Originally logged by {author}]\n{comment}"
                    if comment
                    else f"[Originally logged by {author}]"
                )
                payload = {
                    "timeSpentSeconds": seconds,
                    "started": started,
                    "comment": text_to_adf(note),
                }

                if dry_run:
                    logger.info(
                        "  [DRY] Worklog on %s: %ds by %s",
                        cloud_key, seconds, author,
                    )
                    ok += 1
                    continue

                try:
                    self.client.post(
                        f"/rest/api/3/issue/{cloud_key}/worklog",
                        payload,
                    )
                    self.progress.mark_item_done(
                        "worklogs", log_id,
                    )
                    ok += 1
                except JiraApiError as exc:
                    logger.error(
                        "  Worklog failed on %s: %s",
                        cloud_key, exc,
                    )
                    fail += 1

        logger.info(
            "  Done — Worklogs: %d, Failed: %d", ok, fail,
        )

        if fail == 0:
            self.progress.mark_phase_complete("worklogs")

    # ------------------------------------------------------------------
    # Phase 5 — Attachments
    # ------------------------------------------------------------------

    def _phase_restore_attachments(
        self, backup_dir: str, dry_run: bool,
    ) -> None:
        """Upload attachments, skipping duplicates by filename."""
        if self.progress.is_phase_complete("attachments"):
            logger.info("[PHASE 5] Already complete — skipping.")
            return

        logger.info("\n[PHASE 5] Uploading attachments...")

        att_base = os.path.join(backup_dir, "attachments")
        if not os.path.isdir(att_base):
            logger.warning("  attachments/ dir not found — skipping.")
            return

        ok = fail = skip = 0

        for orig_key in sorted(os.listdir(att_base)):
            issue_dir = os.path.join(att_base, orig_key)
            if not os.path.isdir(issue_dir):
                continue

            cloud_key = self.progress.get_cloud_key(orig_key)
            if not cloud_key:
                logger.debug(
                    "  No mapping for %s — skipping attachments",
                    orig_key,
                )
                continue

            files = sorted(
                f for f in os.listdir(issue_dir)
                if os.path.isfile(os.path.join(issue_dir, f))
            )
            if not files:
                continue

            logger.info(
                "  %s -> %s: %d file(s)",
                orig_key, cloud_key, len(files),
            )

            # Fetch existing attachments to avoid duplicates
            existing = self._get_existing_attachments(cloud_key)

            for fname in files:
                file_path = os.path.join(issue_dir, fname)

                # Strip leading "id_" prefix to recover original
                # filename (backup saves as "123_filename.png")
                clean_name = (
                    fname.split("_", 1)[-1]
                    if "_" in fname
                    else fname
                )

                if clean_name in existing:
                    logger.debug(
                        "    Skip (exists): %s", clean_name,
                    )
                    skip += 1
                    continue

                att_id = f"{orig_key}_{fname}"
                if self.progress.is_item_done(
                    "attachments", att_id,
                ):
                    skip += 1
                    continue

                if dry_run:
                    logger.info(
                        "    [DRY] Upload: %s", clean_name,
                    )
                    ok += 1
                    continue

                try:
                    self.client.upload_file(
                        f"/rest/api/3/issue/{cloud_key}/attachments",
                        file_path,
                        filename=clean_name,
                    )
                    self.progress.mark_item_done(
                        "attachments", att_id,
                    )
                    logger.info("    Uploaded: %s", clean_name)
                    ok += 1
                except (JiraApiError, Exception) as exc:
                    logger.error(
                        "    Upload failed %s: %s",
                        clean_name, exc,
                    )
                    fail += 1

        logger.info(
            "  Done — Uploaded: %d, Skipped: %d, Failed: %d",
            ok, skip, fail,
        )

        if fail == 0:
            self.progress.mark_phase_complete("attachments")

    def _get_existing_attachments(
        self, cloud_key: str,
    ) -> set[str]:
        """Fetch filenames already attached to a Cloud issue."""
        try:
            data = self.client.get(
                f"/rest/api/3/issue/{cloud_key}",
                params={"fields": "attachment"},
            )
            attachments = (
                (data.get("fields") or {})
                .get("attachment") or []
            )
            return {
                a.get("filename", "")
                for a in attachments
                if a.get("filename")
            }
        except JiraApiError:
            return set()
