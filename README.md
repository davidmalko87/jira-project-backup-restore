# Jira Project Backup & Restore

[![CI](https://github.com/davidmalko87/jira-project-backup-restore/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/davidmalko87/jira-project-backup-restore/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/jira-project-backup-restore.svg)](https://pypi.org/project/jira-project-backup-restore/)
[![PyPI downloads](https://img.shields.io/pypi/dm/jira-project-backup-restore.svg)](https://pypi.org/project/jira-project-backup-restore/)
[![Python](https://img.shields.io/pypi/pyversions/jira-project-backup-restore.svg?logo=python&logoColor=white)](https://pypi.org/project/jira-project-backup-restore/)
[![Jira Cloud](https://img.shields.io/badge/Jira-Cloud-0052CC.svg?logo=jira&logoColor=white)](https://www.atlassian.com/software/jira)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)](#)
[![Last commit](https://img.shields.io/github/last-commit/davidmalko87/jira-project-backup-restore.svg)](https://github.com/davidmalko87/jira-project-backup-restore/commits/master)
[![GitHub issues](https://img.shields.io/github/issues/davidmalko87/jira-project-backup-restore.svg)](https://github.com/davidmalko87/jira-project-backup-restore/issues)

Backup and restore individual **Jira Cloud projects** via REST API — issues, comments, worklogs, attachments, boards, and sprints. Fully resumable, with an interactive menu and CLI mode.

---

## Why?

Jira Cloud has no built-in per-project backup/restore. The only native option was the full-instance Backup Manager, which Atlassian [deprecated in March 2026](https://developer.atlassian.com/cloud/jira/platform/changelog/). This tool fills the gap using standard REST API v3 endpoints.

---

## Features

| Feature | Description |
|---|---|
| **Full project backup** | Metadata, components, versions, roles, issues (all fields + changelog), worklogs, attachments, agile boards, sprints |
| **5-phase restore** | Issues (epics first, subtasks last), links, comments, worklogs, attachments |
| **Multi-project** | Backup dozens of projects in a single run |
| **Skip existing** | `--skip-existing` skips projects that already have a complete backup |
| **Auto-cleanup** | Incomplete/partial backup folders are automatically removed before each run |
| **Resumable** | Safely re-run after interruption — already-processed items are skipped |
| **Memory efficient** | Issues stream directly to disk — backup 18 000+ issues on a 1 GB host without OOM |
| **Dry-run mode** | Preview all restore actions without making any API calls |
| **Rate-limit aware** | Exponential backoff with `429 / Retry-After` detection |
| **CSV export** | Export backup data to CSV files for reporting, auditing, and sharing |
| **Backup inspection** | Detailed breakdown of issue types, statuses, priorities, and assignees |
| **Connection test** | Pre-flight check: authentication, project access, and server info |
| **Interactive menu** | Guided workflow with organised sections and post-operation summaries |
| **CLI mode** | `--backup` / `--restore` / `--export-csv` flags for scripted or cron use |

---

## Quick Start

### 1. Install

**Via PyPI (recommended):**

```bash
pip install jira-project-backup-restore
```

**Or clone for development:**

```bash
git clone https://github.com/davidmalko87/jira-project-backup-restore.git
cd jira-project-backup-restore
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your Jira Cloud credentials:

```ini
JIRA_URL=https://your-domain.atlassian.net
JIRA_EMAIL=you@example.com
JIRA_API_TOKEN=your-api-token
```

> Generate an API token at [id.atlassian.com/manage-api-tokens](https://id.atlassian.com/manage-api-tokens)

### 3. Run

**Interactive menu:**

```bash
python main.py
```

```
==================================================
  Jira Backup & Restore Tool v1.3.2
==================================================
  Instance : https://your-domain.atlassian.net
  Auth     : API Token
  Backups  : ./backups

  --- Backup & Restore ---
  1) Backup project(s)
  2) Restore project from backup

  --- Browse & Analyze ---
  3) List existing backups
  4) Validate backup integrity
  5) Upload attachments only
  6) Export backup to CSV
  7) Inspect backup details

  --- Settings & Tools ---
  8) Test Jira connection
  9) Show current configuration
  10) Cleanup incomplete backups
  0) Exit
```

**CLI — backup:**

```bash
python main.py --backup PROJ
python main.py --backup PROJ1,PROJ2
python main.py --backup PROJ1,PROJ2 --skip-existing
```

**CLI — restore:**

```bash
python main.py --restore backups/PROJ_20260322_143000 --target NEWPROJ
python main.py --restore backups/PROJ_20260322_143000 --target NEWPROJ --dry-run
```

**CLI — export to CSV:**

```bash
python main.py --export-csv backups/PROJ_20260322_143000
python main.py --export-csv backups/PROJ_20260322_143000 --output-dir /tmp/report
```

---

## What Gets Backed Up

| File | Contents |
|---|---|
| `project_meta.json` | Project config — name, lead, category, permission scheme |
| `components.json` | All project components |
| `versions.json` | All fix versions |
| `roles.json` | Role-to-member mappings |
| `issues.json` | All issues — every field, changelog history |
| `worklogs/worklogs.json` | Time tracking entries per issue |
| `attachments/<KEY>/` | Binary attachment files, streamed to disk |
| `boards.json` | Agile board list |
| `board_<id>_config.json` | Board columns and swimlanes |
| `board_<id>_sprints.json` | Sprint history |
| `manifest.json` | File index — presence marks the backup as complete |

---

## Restore Phases

Each phase can be toggled individually and is fully resumable via `restore_progress.json`:

| Phase | What happens | Endpoint |
|---|---|---|
| 1 | Create issues — epics first, then regular, then subtasks | `POST /rest/api/3/issue` |
| 2 | Restore issue links (outward only, no duplicates) | `POST /rest/api/3/issueLink` |
| 3 | Add comments — original author and date prepended as text | `POST /rest/api/3/issue/{key}/comment` |
| 4 | Add worklogs — original author prepended as text | `POST /rest/api/3/issue/{key}/worklog` |
| 5 | Upload attachments — skips duplicates by filename | `POST /rest/api/3/issue/{key}/attachments` |

Issue key mapping between source and target is saved in `key_mapping.json` inside the backup directory.

---

## Known Limitations

These are Jira Cloud REST API constraints — not tool limitations:

| Data | Status | Notes |
|---|---|---|
| Timestamps (created/updated) | Not restorable | Cloud API blocks setting these fields |
| Changelog / history | Backup only | No write endpoint exists |
| Comment / worklog author | Text attribution | `[Originally by Name on Date]` prepended |
| Reporter / Assignee | Conditional | Restored only if the user's email exists in the target instance |
| Issue status | Resets to default | Workflow transitions not yet automated |
| Issue keys (e.g. `KEY-123`) | Reassigned | Cloud assigns new keys; old→new mapping is saved |

---

## Project Structure

```
jira-project-backup-restore/
├── main.py                   # Entry point — interactive menu + CLI flags
├── .env.example              # Configuration template
├── requirements.txt          # Python dependencies
│
├── jira_tool/
│   ├── config.py             # .env loader and validation
│   ├── auth.py               # Session builder (API token / cookie auth)
│   ├── api_client.py         # HTTP client with retry and rate-limit handling
│   ├── backup.py             # BackupManager — orchestrates full project backup
│   ├── restore.py            # RestoreManager — 5-phase restore
│   ├── export.py             # CSV export and backup statistics
│   ├── attachments.py        # Standalone attachment uploader
│   ├── adf.py                # Atlassian Document Format helpers
│   ├── progress.py           # Resumability tracker
│   ├── utils.py              # Logging, JSON I/O, utilities
│   ├── cli.py                # Console-script entry point
│   └── menu.py               # Interactive CLI menu
│
└── backups/                  # Backup output directory (gitignored)
    └── PROJ_20260322_143000/
        ├── manifest.json     # Completion marker + file index
        ├── issues.json
        ├── attachments/
        └── ...
```

---

## Configuration Reference

All settings live in `.env` (copy from `.env.example`):

| Variable | Required | Default | Description |
|---|---|---|---|
| `JIRA_URL` | Yes | — | Jira Cloud base URL (no trailing slash) |
| `JIRA_EMAIL` | Yes* | — | Account email for API token auth |
| `JIRA_API_TOKEN` | Yes* | — | API token — [generate here](https://id.atlassian.com/manage-api-tokens) |
| `JIRA_COOKIE_HEADER` | Alt* | — | Full `Cookie:` header value for SSO auth |
| `JIRA_VERIFY_SSL` | No | `true` | Set `false` to skip SSL verification |
| `BACKUP_ROOT` | No | `./backups` | Directory where backups are written |
| `PAGE_SIZE` | No | `100` | Issues per API page (max 100) |
| `MAX_RETRIES` | No | `3` | Retry count on transient failures |
| `READ_TIMEOUT` | No | `30` | HTTP read timeout in seconds |
| `API_DELAY` | No | `0.2` | Seconds to wait between API calls |
| `INCLUDE_ATTACHMENTS` | No | `true` | Download attachment binary files |
| `INCLUDE_CHANGELOG` | No | `true` | Include field change history in issues |
| `INCLUDE_WORKLOGS` | No | `true` | Include time tracking entries |
| `LEGACY_KEY_JQL_TEMPLATE` | No | — | JQL template for standalone attachment upload |

> \* Either `JIRA_EMAIL` + `JIRA_API_TOKEN` **or** `JIRA_COOKIE_HEADER` is required.

---

## Requirements

- Python **3.10+**
- [`requests`](https://pypi.org/project/requests/) >= 2.28
- [`python-dotenv`](https://pypi.org/project/python-dotenv/) >= 1.0

---

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the full version history.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the versioning policy and how to bump the version when making changes.

## License

[MIT](LICENSE)
