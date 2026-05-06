# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.3.2] - 2026-05-06

### Fixed
- **Python 3.10/3.11 compatibility** ([#25](https://github.com/davidmalko87/jira-project-backup-restore/issues/25)) — `shutil.rmtree(onexc=...)` was introduced in Python 3.12, causing `TypeError` on older versions when cleaning up incomplete backups. Now uses `onerror` on Python < 3.12.
- **SSL warning spam** — when `JIRA_VERIFY_SSL=false` (e.g. behind a corporate proxy), every API call printed an `InsecureRequestWarning` to the console, making output unreadable. Warnings are now suppressed when the user explicitly disables SSL verification.

### Added
- **Worklog progress display** — `_backup_worklogs` now logs progress every 100 issues (e.g. `Worklogs: 300 / 17800 checked (42 with entries)`), matching the existing issue-fetch progress and giving feedback on long-running backups.

---

## [1.3.1] - 2026-05-02

### Fixed
- **Memory exhaustion on large projects** ([#25](https://github.com/davidmalko87/jira-project-backup-restore/issues/25)) — `_backup_issues` previously buffered every issue in memory before writing `issues.json`, which could OOM-kill the process on small hosts when backing up projects with thousands of issues (e.g. 18k+ issues on a 1 GB RAM box). Issues are now streamed page-by-page directly to disk, keeping RAM usage flat regardless of project size. Only a lightweight per-issue summary (key + attachment list) is retained in memory for the downstream worklog and attachment phases. Thanks to [@LexPS75](https://github.com/LexPS75) for the report and proposed fix.

---

## [1.3.0] - 2026-04-13

### Added
- **Export backup to CSV** — new menu option and `--export-csv` CLI flag to export issues, comments, worklogs, components, and versions to CSV files for reporting and analysis outside of Jira.
- **Inspect backup details** — new menu option showing detailed breakdown of issue types, statuses, priorities, and top assignees with visual bar charts.
- **Test Jira connection** — new menu option that runs a 3-step pre-flight check: authentication, project access, and server info.
- **Show current configuration** — new menu option to review all active settings without opening the `.env` file.
- **Post-backup summary** — after each backup completes, a summary is displayed with issue, comment, attachment, worklog, component, and version counts plus total disk size.
- **`--output-dir`** CLI flag to control the CSV export output directory.
- New `jira_tool/export.py` module with CSV export and backup statistics/analysis functions.

### Changed
- Reorganised interactive menu into three logical sections: *Backup & Restore*, *Browse & Analyze*, and *Settings & Tools* (now 10 options, up from 6).
- Backup listing now shows disk size per backup and total size across all backups.
- All menu operations now pause with "Press Enter to return to menu" before returning.
- Backup selection prompts now accept `b` to go back without selecting.
- Restore confirmation now displays which phases are selected before proceeding.
- Menu header now shows authentication method and backup directory path.

---

## [1.2.7] - 2026-03-28

### Fixed
- Add missing `jira_tool/cli.py` entry point — the `jira-backup` console script (installed via pip) was broken because `pyproject.toml` referenced `jira_tool.cli:main` but the module did not exist.
- Sync `__init__.py` version with `pyproject.toml` (was stuck at 1.2.5).
- Update interactive menu banner and README to show the correct version.

---

## [1.2.6] - 2026-03-27

### Changed
- Add author email, keywords, and `Development Status :: 5 - Production/Stable` classifier to package metadata
- Fix pyproject.toml indentation

---

## [1.2.5] - 2026-03-27

### Fixed
- Fixed deprecated `pyproject.toml` license table format — changed to SPDX string (`license = "MIT"`) and removed deprecated license classifier, resolving setuptools deprecation warnings during build.

---

## [1.2.4] - 2026-03-27

### Fixed
- `PermissionError` (WinError 5) on Windows when deleting incomplete backup folders (e.g. on Google Drive). The cleanup now clears read-only file attributes before removal and gracefully skips any folder that is still locked by another process (e.g. Google Drive sync), logging a warning instead of crashing.

---

## [1.2.3] - 2026-03-27

### Added
- Menu option **6) Cleanup incomplete backups**: lists all folders without `manifest.json`, confirms with the user, and deletes them in one step.

---

## [1.2.2] - 2026-03-27

### Added
- Automatic cleanup of incomplete backup folders (no `manifest.json`) before each backup run.
  - Per-project: incomplete folders for the target project are deleted before a new backup starts.
  - Global: all incomplete folders across all projects are removed at the start of a multi-project backup run.
- `cleanup_all_incomplete()` public method on `BackupManager` for programmatic use.

---

## [1.2.1] - 2026-03-26

### Fixed
- JQL reserved word error when project key matches a JQL keyword (e.g. `AS`).

---

## [1.2.0] - 2026-03-26

### Added
- `--skip-existing` CLI flag and interactive menu prompt to skip projects that already have a complete backup, enabling safe incremental re-runs.

---

## [1.1.0] - 2026-03-26

### Added
- Configurable `READ_TIMEOUT` setting in `.env` / `JiraConfig` so long-running API calls no longer time out on large projects.

---

## [1.0.5] - 2026-03-23

### Fixed
- Assignee, reporter, and description fields now fall back gracefully when the value is missing or the account cannot be resolved on the target instance.

---

## [1.0.4] - 2026-03-23

### Fixed
- `--dry-run` mode no longer persists progress state to disk.
- Assignee lookup falls back to `None` instead of raising when the user is not found.
- Added metadata comment to restored issues linking back to the original issue key.

---

## [1.0.3] - 2026-03-23

### Fixed
- Search/JQL pagination now uses `nextPageToken` instead of `startAt` as required by Jira REST API v3.

---

## [1.0.2] - 2026-03-23

### Fixed
- Search/JQL `expand` parameter changed from array to comma-separated string to match the REST API v3 contract.

---

## [1.0.1] - 2026-03-23

### Changed
- Migrated all backup endpoints from Jira REST API v2 to v3.

---

## [1.0.0] - 2026-03-22

### Added
- Initial release: full backup and restore of Jira projects via REST API.
- Backup of project metadata, components, versions, roles, issues (with changelog), worklogs, attachments, and agile board configuration.
- Interactive CLI menu and non-interactive `--backup` / `--restore` modes.
- `--dry-run` flag for restore preview.
- Resumable restore via `progress.json` checkpoint file.
