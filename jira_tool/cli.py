#!/usr/bin/env python3
# jira_tool/cli.py — Console-script entry point for installed package
# Author: David Malko

"""CLI entry point used by the ``jira-backup`` console script (pyproject.toml).

When running from a clone, use ``python main.py`` instead.
"""

import argparse
import sys

from jira_tool.api_client import JiraClient
from jira_tool.auth import build_session
from jira_tool.backup import BackupManager
from jira_tool.config import load_config
from jira_tool.export import export_backup_to_csv
from jira_tool.menu import run_menu
from jira_tool.progress import ProgressTracker
from jira_tool.restore import RestoreManager
from jira_tool.utils import setup_logging


def main() -> None:
    """Parse args and launch menu or direct action."""
    parser = argparse.ArgumentParser(
        description="Jira Project Backup & Restore Tool",
    )
    parser.add_argument(
        "--env", default=None,
        help="Path to .env config file (default: .env in current dir)",
    )
    parser.add_argument(
        "--backup",
        help="Backup project key(s), comma-separated (non-interactive)",
    )
    parser.add_argument(
        "--restore",
        help="Restore from backup directory (non-interactive)",
    )
    parser.add_argument(
        "--target",
        help="Target project key for restore",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Log actions without making API calls",
    )
    parser.add_argument(
        "--skip-existing", action="store_true",
        help="Skip projects that already have a complete backup in BACKUP_ROOT",
    )
    parser.add_argument(
        "--export-csv",
        help="Export backup directory to CSV files (non-interactive)",
    )
    parser.add_argument(
        "--output-dir",
        help="Output directory for CSV export (default: <backup>/csv_export)",
    )

    args = parser.parse_args()

    config = load_config(args.env)
    logger = setup_logging(log_dir=config.backup_root)

    # Non-interactive: CSV export
    if args.export_csv:
        import os
        backup_dir = args.export_csv
        if not os.path.isdir(backup_dir):
            print(f"[!] Backup directory not found: {backup_dir}")
            sys.exit(1)
        output_dir = args.output_dir or os.path.join(
            backup_dir, "csv_export",
        )
        results = export_backup_to_csv(backup_dir, output_dir)
        print(f"\nExport complete — {len(results)} CSV file(s):")
        for filename, count in results.items():
            print(f"  {filename}: {count} rows")
        print(f"\nOutput: {output_dir}")
        return

    # Non-interactive: backup
    if args.backup:
        keys = [
            k.strip().upper()
            for k in args.backup.split(",")
            if k.strip()
        ]
        session = build_session(config)
        client = JiraClient(session, config.jira_url, config)
        manager = BackupManager(client, config)

        if len(keys) == 1:
            if args.skip_existing:
                existing = manager._find_existing_backup(keys[0])
                if existing:
                    logger.info(
                        "[SKIP] %s — backup exists: %s", keys[0], existing,
                    )
                    return
            manager.backup_project(keys[0])
        else:
            manager.backup_projects(keys, skip_existing=args.skip_existing)
        return

    # Non-interactive: restore
    if args.restore:
        if not args.target:
            print("[!] --target is required with --restore")
            sys.exit(1)

        session = build_session(config)
        client = JiraClient(session, config.jira_url, config)
        progress = ProgressTracker(
            args.restore, dry_run=args.dry_run,
        )
        manager = RestoreManager(client, config, progress)

        manager.restore_project(
            args.restore,
            args.target.upper(),
            dry_run=args.dry_run,
        )
        return

    # Interactive mode
    run_menu(config)
