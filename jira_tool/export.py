# export.py — Export backup data to CSV for reporting and analysis
# Author: David Malko

"""Export Jira backup data to CSV files.

Generates human-readable CSV reports from backup JSON files,
useful for auditing, sharing, and analysis outside of Jira.
"""

import csv
import logging
import os
from collections import Counter

from jira_tool.utils import load_json

logger = logging.getLogger("jira_tool")


def export_backup_to_csv(backup_dir: str, output_dir: str) -> dict[str, int]:
    """Export all backup data to CSV files.

    Args:
        backup_dir: Path to backup directory containing JSON files.
        output_dir: Path to write CSV files into.

    Returns:
        Dict mapping CSV filename to row count written.
    """
    os.makedirs(output_dir, exist_ok=True)
    results: dict[str, int] = {}

    issues_path = os.path.join(backup_dir, "issues.json")
    if os.path.exists(issues_path):
        issues = load_json(issues_path)
        count = _export_issues_csv(issues, output_dir)
        results["issues.csv"] = count

        count = _export_comments_csv(issues, output_dir)
        results["comments.csv"] = count
    else:
        logger.warning("  issues.json not found — skipping issue/comment export.")

    worklogs_path = os.path.join(backup_dir, "worklogs", "worklogs.json")
    if os.path.exists(worklogs_path):
        worklogs = load_json(worklogs_path)
        count = _export_worklogs_csv(worklogs, output_dir)
        results["worklogs.csv"] = count
    else:
        logger.info("  No worklogs found — skipping worklog export.")

    components_path = os.path.join(backup_dir, "components.json")
    if os.path.exists(components_path):
        components = load_json(components_path)
        count = _export_components_csv(components, output_dir)
        results["components.csv"] = count

    versions_path = os.path.join(backup_dir, "versions.json")
    if os.path.exists(versions_path):
        versions = load_json(versions_path)
        count = _export_versions_csv(versions, output_dir)
        results["versions.csv"] = count

    return results


def _export_issues_csv(issues: list[dict], output_dir: str) -> int:
    """Export issues to CSV."""
    path = os.path.join(output_dir, "issues.csv")
    headers = [
        "Key", "Summary", "Type", "Status", "Priority",
        "Assignee", "Reporter", "Created", "Updated",
        "Resolution", "Resolved", "Due Date",
        "Labels", "Components", "Fix Versions",
        "Story Points", "Epic Link", "Parent",
        "Comment Count", "Attachment Count",
    ]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for issue in issues:
            fields = issue.get("fields", {}) or {}
            writer.writerow([
                issue.get("key", ""),
                fields.get("summary", ""),
                _nested(fields, "issuetype", "name"),
                _nested(fields, "status", "name"),
                _nested(fields, "priority", "name"),
                _nested(fields, "assignee", "displayName"),
                _nested(fields, "reporter", "displayName"),
                (fields.get("created") or "")[:19],
                (fields.get("updated") or "")[:19],
                _nested(fields, "resolution", "name"),
                (fields.get("resolutiondate") or "")[:19],
                fields.get("duedate", ""),
                "; ".join(fields.get("labels") or []),
                "; ".join(
                    c.get("name", "") for c in (fields.get("components") or [])
                ),
                "; ".join(
                    v.get("name", "") for v in (fields.get("fixVersions") or [])
                ),
                _story_points(fields),
                _epic_link(fields),
                _nested(fields, "parent", "key"),
                len(
                    ((fields.get("comment") or {}).get("comments") or [])
                ),
                len(fields.get("attachment") or []),
            ])

    logger.info("    Exported %d issues to issues.csv", len(issues))
    return len(issues)


def _export_comments_csv(issues: list[dict], output_dir: str) -> int:
    """Export all comments to CSV."""
    path = os.path.join(output_dir, "comments.csv")
    headers = [
        "Issue Key", "Comment #", "Author", "Created", "Updated", "Body Preview",
    ]
    count = 0

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for issue in issues:
            key = issue.get("key", "")
            fields = issue.get("fields", {}) or {}
            comments = (
                (fields.get("comment") or {}).get("comments") or []
            )

            for i, comment in enumerate(comments, 1):
                body = comment.get("body") or ""
                if isinstance(body, dict):
                    body = _extract_text_preview(body)
                preview = (body[:200] + "...") if len(body) > 200 else body
                preview = preview.replace("\n", " ").replace("\r", "")

                writer.writerow([
                    key,
                    i,
                    _nested(comment, "author", "displayName"),
                    (comment.get("created") or "")[:19],
                    (comment.get("updated") or "")[:19],
                    preview,
                ])
                count += 1

    logger.info("    Exported %d comments to comments.csv", count)
    return count


def _export_worklogs_csv(worklogs: dict, output_dir: str) -> int:
    """Export worklogs to CSV."""
    path = os.path.join(output_dir, "worklogs.csv")
    headers = [
        "Issue Key", "Author", "Started", "Time Spent (seconds)",
        "Time Spent (human)", "Comment Preview",
    ]
    count = 0

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        for issue_key, logs in worklogs.items():
            for log in logs:
                seconds = log.get("timeSpentSeconds", 0)
                comment = log.get("comment") or ""
                if isinstance(comment, dict):
                    comment = _extract_text_preview(comment)
                preview = (comment[:150] + "...") if len(comment) > 150 else comment
                preview = preview.replace("\n", " ").replace("\r", "")

                writer.writerow([
                    issue_key,
                    _nested(log, "author", "displayName"),
                    (log.get("started") or "")[:19],
                    seconds,
                    _format_duration(seconds),
                    preview,
                ])
                count += 1

    logger.info("    Exported %d worklogs to worklogs.csv", count)
    return count


def _export_components_csv(components: list[dict], output_dir: str) -> int:
    """Export components to CSV."""
    path = os.path.join(output_dir, "components.csv")
    headers = ["Name", "Description", "Lead"]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for comp in components:
            writer.writerow([
                comp.get("name", ""),
                comp.get("description", ""),
                _nested(comp, "lead", "displayName"),
            ])

    return len(components)


def _export_versions_csv(versions: list[dict], output_dir: str) -> int:
    """Export versions to CSV."""
    path = os.path.join(output_dir, "versions.csv")
    headers = ["Name", "Description", "Released", "Release Date", "Start Date"]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for ver in versions:
            writer.writerow([
                ver.get("name", ""),
                ver.get("description", ""),
                ver.get("released", False),
                ver.get("releaseDate", ""),
                ver.get("startDate", ""),
            ])

    return len(versions)


def get_backup_statistics(backup_dir: str) -> dict:
    """Compute detailed statistics from a backup directory.

    Args:
        backup_dir: Path to backup directory.

    Returns:
        Dict with keys: issue_count, type_counts, status_counts,
        priority_counts, comment_count, attachment_count,
        worklog_count, component_count, version_count,
        total_size_bytes, assignees.
    """
    stats: dict = {
        "issue_count": 0,
        "type_counts": Counter(),
        "status_counts": Counter(),
        "priority_counts": Counter(),
        "comment_count": 0,
        "attachment_count": 0,
        "worklog_count": 0,
        "component_count": 0,
        "version_count": 0,
        "total_size_bytes": 0,
        "assignees": Counter(),
    }

    # Total directory size
    for root, _, files in os.walk(backup_dir):
        for fname in files:
            fpath = os.path.join(root, fname)
            try:
                stats["total_size_bytes"] += os.path.getsize(fpath)
            except OSError:
                pass

    # Issues
    issues_path = os.path.join(backup_dir, "issues.json")
    if os.path.exists(issues_path):
        issues = load_json(issues_path)
        stats["issue_count"] = len(issues)

        for issue in issues:
            fields = issue.get("fields", {}) or {}
            itype = _nested(fields, "issuetype", "name") or "Unknown"
            stats["type_counts"][itype] += 1

            status = _nested(fields, "status", "name") or "Unknown"
            stats["status_counts"][status] += 1

            priority = _nested(fields, "priority", "name") or "None"
            stats["priority_counts"][priority] += 1

            assignee = _nested(fields, "assignee", "displayName") or "Unassigned"
            stats["assignees"][assignee] += 1

            comments = (
                (fields.get("comment") or {}).get("comments") or []
            )
            stats["comment_count"] += len(comments)

            attachments = fields.get("attachment") or []
            stats["attachment_count"] += len(attachments)

    # Worklogs
    worklogs_path = os.path.join(backup_dir, "worklogs", "worklogs.json")
    if os.path.exists(worklogs_path):
        worklogs = load_json(worklogs_path)
        for logs in worklogs.values():
            stats["worklog_count"] += len(logs)

    # Components
    comp_path = os.path.join(backup_dir, "components.json")
    if os.path.exists(comp_path):
        stats["component_count"] = len(load_json(comp_path))

    # Versions
    ver_path = os.path.join(backup_dir, "versions.json")
    if os.path.exists(ver_path):
        stats["version_count"] = len(load_json(ver_path))

    return stats


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _nested(data: dict, key1: str, key2: str) -> str:
    """Safely extract nested dict value."""
    return ((data.get(key1) or {}).get(key2) or "")


def _story_points(fields: dict) -> str:
    """Extract story points from known custom fields."""
    for key in ("story_points", "customfield_10016"):
        val = fields.get(key)
        if val is not None:
            return str(val)
    return ""


def _epic_link(fields: dict) -> str:
    """Extract epic link from known custom fields."""
    epic = fields.get("customfield_10008")
    if isinstance(epic, dict):
        return epic.get("key", "")
    if isinstance(epic, str):
        return epic
    return ""


def _extract_text_preview(adf: dict) -> str:
    """Extract plain text from ADF body for CSV preview."""
    parts: list[str] = []

    def _walk(node) -> None:
        if isinstance(node, list):
            for item in node:
                _walk(item)
            return
        if not isinstance(node, dict):
            return
        if node.get("type") == "text":
            parts.append(node.get("text", ""))
        for child in node.get("content", []):
            _walk(child)

    _walk(adf)
    return " ".join(parts)


def _format_duration(seconds: int) -> str:
    """Format seconds into human-readable duration."""
    if seconds <= 0:
        return "0m"
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    if hours > 0:
        return f"{hours}h {minutes}m" if minutes else f"{hours}h"
    return f"{minutes}m"


def format_size(size_bytes: int) -> str:
    """Format byte count into human-readable size."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
