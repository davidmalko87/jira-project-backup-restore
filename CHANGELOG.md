# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
