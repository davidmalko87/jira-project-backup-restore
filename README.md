# jira-project-backup-restore

Backup and restore individual Jira Cloud projects via REST API. Full project-level backup with issues, comments, worklogs, attachments, boards, and sprints — plus resumable restore into any Jira Cloud instance.

## Why?

Jira Cloud has no built-in per-project backup/restore. The only native option was the full-instance Backup Manager, which Atlassian [deprecated in March 2026](https://developer.atlassian.com/cloud/jira/platform/changelog/). This tool fills the gap using standard REST API v2/v3 endpoints.

## Features

- **Full project backup** — metadata, components, versions, roles, issues (all fields + changelog), worklogs, attachments, agile boards, and sprints
- **5-phase restore** — issues (epics first, subtasks last), links, comments, worklogs, attachments
- **Multi-project support** — backup multiple projects in one run
- **Skip existing** — `--skip-existing` flag skips projects that already have a complete backup
- **Auto-cleanup** — incomplete/partial backup folders are automatically removed before each run
- **Resumable** — safely re-run after interruption; already-processed items are skipped
- **Dry-run mode** — preview all restore actions without making API calls
- **Rate-limit handling** — exponential backoff with 429/Retry-After detection
- **Interactive menu** — guided workflow for backup, restore, validation, attachment upload, and cleanup
- **CLI mode** — `--backup` / `--restore` flags for scripted or cron use
- **Standalone attachment uploader** — for cases where issues were restored by another tool

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` with your Jira Cloud URL and API token:

```ini
JIRA_URL=https://your-domain.atlassian.net
JIRA_EMAIL=you@example.com
JIRA_API_TOKEN=your-api-token
```

Generate an API token at: https://id.atlassian.com/manage-api-tokens

### 3. Run

**Interactive menu:**

```bash
python main.py
```

**Non-interactive (backup):**

```bash
python main.py --backup PROJ
python main.py --backup PROJ1,PROJ2
python main.py --backup PROJ1,PROJ2 --skip-existing   # skip already-backed-up projects
```

**Non-interactive (restore):**

```bash
python main.py --restore backups/PROJ_20260322_143000 --target NEWPROJ
python main.py --restore backups/PROJ_20260322_143000 --target NEWPROJ --dry-run
```

## What Gets Backed Up

| Data | File | Notes |
|---|---|---|
| Project config | `project_meta.json` | Name, lead, category, scheme |
| Components | `components.json` | All project components |
| Versions | `versions.json` | All fix versions |
| Roles | `roles.json` | Role-to-member mappings |
| Issues | `issues.json` | All fields, changelog history |
| Worklogs | `worklogs/worklogs.json` | Time tracking entries per issue |
| Attachments | `attachments/<KEY>/` | Binary files, streamed to disk |
| Boards | `boards.json` | Agile board list |
| Board config | `board_<id>_config.json` | Columns, swimlanes |
| Sprints | `board_<id>_sprints.json` | Sprint history |
| Manifest | `manifest.json` | File index with metadata |

## Restore Phases

Each phase can be toggled individually and is fully resumable:

| Phase | What | API |
|---|---|---|
| 1 | Create issues (epics -> regular -> subtasks) | `POST /rest/api/3/issue` |
| 2 | Restore issue links (outward-only, no duplicates) | `POST /rest/api/3/issueLink` |
| 3 | Add comments (author + date prepended as text) | `POST /rest/api/3/issue/{key}/comment` |
| 4 | Add worklogs (author prepended as text) | `POST /rest/api/3/issue/{key}/worklog` |
| 5 | Upload attachments (skip duplicates by filename) | `POST /rest/api/3/issue/{key}/attachments` |

Progress is tracked in `key_mapping.json` and `restore_progress.json` inside the backup directory.

## Known Limitations

These are Jira Cloud REST API constraints — not tool limitations:

| Data | Status | Notes |
|---|---|---|
| Timestamps (created/updated) | Not restorable | Cloud blocks setting these fields |
| Changelog / history | Backup only | No import endpoint exists |
| Comment / worklog author | Text attribution | `[Originally by Name on Date]` prepended |
| Reporter / Assignee | Conditional | Restored only if user email matches in Cloud |
| Issue status | Resets to default | Transitions phase planned for future |
| Issue keys (e.g. KEY-123) | Reassigned | Cloud assigns new keys; mapping saved |

## Project Structure

```
jira-backup-restore/
├── main.py                   # Entry point (menu + CLI)
├── .env.example              # Configuration template
├── requirements.txt          # Python dependencies
│
├── jira_tool/
│   ├── config.py             # .env loader + validation
│   ├── auth.py               # Session builder (token / cookie auth)
│   ├── api_client.py         # HTTP client with retry + rate limiting
│   ├── backup.py             # BackupManager
│   ├── restore.py            # RestoreManager (5-phase)
│   ├── attachments.py        # Standalone attachment uploader
│   ├── adf.py                # Atlassian Document Format helpers
│   ├── progress.py           # Resumability tracker
│   ├── utils.py              # Logging, JSON I/O, utilities
│   └── menu.py               # Interactive CLI menu
│
└── backups/                  # Backup output (gitignored)
```

## Configuration Reference

All settings are in `.env`:

| Variable | Required | Default | Description |
|---|---|---|---|
| `JIRA_URL` | Yes | — | Jira Cloud URL (no trailing slash) |
| `JIRA_EMAIL` | Yes* | — | Email for API token auth |
| `JIRA_API_TOKEN` | Yes* | — | API token ([generate here](https://id.atlassian.com/manage-api-tokens)) |
| `JIRA_COOKIE_HEADER` | Alt* | — | Cookie auth for SSO (alternative to token) |
| `JIRA_VERIFY_SSL` | No | `true` | Set `false` for self-signed certs |
| `BACKUP_ROOT` | No | `./backups` | Backup output directory |
| `PAGE_SIZE` | No | `100` | Issues per API page (max 100) |
| `MAX_RETRIES` | No | `3` | Retry count for failed requests |
| `READ_TIMEOUT` | No | `30` | HTTP read timeout in seconds |
| `API_DELAY` | No | `0.2` | Seconds between API calls |
| `INCLUDE_ATTACHMENTS` | No | `true` | Download attachment files |
| `INCLUDE_CHANGELOG` | No | `true` | Include field change history |
| `INCLUDE_WORKLOGS` | No | `true` | Include time tracking |
| `LEGACY_KEY_JQL_TEMPLATE` | No | — | JQL for standalone attachment upload |

\* Either `JIRA_EMAIL` + `JIRA_API_TOKEN` or `JIRA_COOKIE_HEADER` is required.

## Interactive Menu

| Option | Description |
|---|---|
| 1 | Backup one or more projects |
| 2 | Restore a project from backup |
| 3 | List all existing backups |
| 4 | Validate backup integrity (checks files against manifest) |
| 5 | Upload attachments only |
| 6 | Cleanup incomplete backups (remove folders with no manifest) |
| 0 | Exit |

## Requirements

- Python 3.10+
- `requests` >= 2.28
- `python-dotenv` >= 1.0

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for the full version history.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the versioning policy and how to bump the version when making changes.

## License

MIT
