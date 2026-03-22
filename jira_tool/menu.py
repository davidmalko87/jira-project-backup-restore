# menu.py — Interactive CLI menu for Jira Backup & Restore Tool
# Author: David Malko

"""Interactive menu for guided backup, restore, and utility operations."""

import logging
import os
import sys

from jira_tool import __version__
from jira_tool.api_client import JiraClient
from jira_tool.attachments import AttachmentUploader
from jira_tool.auth import build_session
from jira_tool.backup import BackupManager
from jira_tool.config import JiraConfig
from jira_tool.progress import ProgressTracker
from jira_tool.restore import RestoreManager
from jira_tool.utils import load_json

logger = logging.getLogger("jira_tool")


def run_menu(config: JiraConfig) -> None:
    """Main interactive menu loop.

    Args:
        config: Validated JiraConfig instance.
    """
    while True:
        _print_header(config)
        choice = input("  Choice: ").strip()

        if choice == "1":
            _menu_backup(config)
        elif choice == "2":
            _menu_restore(config)
        elif choice == "3":
            _menu_list_backups(config)
        elif choice == "4":
            _menu_validate_backup(config)
        elif choice == "5":
            _menu_upload_attachments(config)
        elif choice == "0":
            print("\nGoodbye.")
            sys.exit(0)
        else:
            print("\n  Invalid choice. Try again.\n")


def _print_header(config: JiraConfig) -> None:
    """Display the main menu."""
    print(f"\n{'=' * 45}")
    print(f"  Jira Backup & Restore Tool v{__version__}")
    print(f"{'=' * 45}")
    print(f"  Instance: {config.jira_url}")
    print()
    print("  1) Backup project(s)")
    print("  2) Restore project from backup")
    print("  3) List existing backups")
    print("  4) Validate backup integrity")
    print("  5) Upload attachments only")
    print("  0) Exit")
    print()


# ------------------------------------------------------------------
# Menu actions
# ------------------------------------------------------------------

def _menu_backup(config: JiraConfig) -> None:
    """Prompt for project key(s) and run backup."""
    print("\n--- Backup Project(s) ---")
    keys_input = input(
        "  Enter project key(s) (comma-separated): ",
    ).strip()

    if not keys_input:
        print("  No keys entered. Returning to menu.")
        return

    keys = [k.strip().upper() for k in keys_input.split(",") if k.strip()]
    print(f"\n  Projects to backup: {', '.join(keys)}")
    confirm = input("  Proceed? (y/n): ").strip().lower()
    if confirm != "y":
        print("  Cancelled.")
        return

    session = build_session(config)
    client = JiraClient(session, config.jira_url, config)
    manager = BackupManager(client, config)

    if len(keys) == 1:
        manager.backup_project(keys[0])
    else:
        manager.backup_projects(keys)


def _menu_restore(config: JiraConfig) -> None:
    """List backups, pick one, and run restore."""
    print("\n--- Restore Project ---")

    backups = _list_backup_dirs(config.backup_root)
    if not backups:
        print("  No backups found.")
        return

    print("  Available backups:")
    for i, (name, info) in enumerate(backups, 1):
        print(f"    {i}) {name}  ({info})")

    pick = input("\n  Select backup number: ").strip()
    try:
        idx = int(pick) - 1
        backup_name, _ = backups[idx]
    except (ValueError, IndexError):
        print("  Invalid selection.")
        return

    backup_dir = os.path.join(config.backup_root, backup_name)

    target_key = input(
        "  Target project key in Cloud: ",
    ).strip().upper()
    if not target_key:
        print("  No project key entered. Cancelled.")
        return

    dry_run_input = input(
        "  Dry run? (y/n) [n]: ",
    ).strip().lower()
    dry_run = dry_run_input == "y"

    # Ask which phases to run
    phases = _ask_phases()

    print(f"\n  Backup:  {backup_dir}")
    print(f"  Target:  {target_key}")
    print(f"  Dry run: {dry_run}")
    confirm = input("  Proceed? (y/n): ").strip().lower()
    if confirm != "y":
        print("  Cancelled.")
        return

    session = build_session(config)
    client = JiraClient(session, config.jira_url, config)
    progress = ProgressTracker(backup_dir)
    manager = RestoreManager(client, config, progress)

    manager.restore_project(
        backup_dir, target_key,
        dry_run=dry_run, phases=phases,
    )


def _menu_list_backups(config: JiraConfig) -> None:
    """Show existing backups with summary info."""
    print("\n--- Existing Backups ---")

    backups = _list_backup_dirs(config.backup_root)
    if not backups:
        print("  No backups found in:", config.backup_root)
        return

    for name, info in backups:
        print(f"  {name}  ({info})")

    print(f"\n  Total: {len(backups)} backup(s)")


def _menu_validate_backup(config: JiraConfig) -> None:
    """Check manifest against actual files."""
    print("\n--- Validate Backup ---")

    backups = _list_backup_dirs(config.backup_root)
    if not backups:
        print("  No backups found.")
        return

    print("  Available backups:")
    for i, (name, info) in enumerate(backups, 1):
        print(f"    {i}) {name}  ({info})")

    pick = input("\n  Select backup number: ").strip()
    try:
        idx = int(pick) - 1
        backup_name, _ = backups[idx]
    except (ValueError, IndexError):
        print("  Invalid selection.")
        return

    backup_dir = os.path.join(config.backup_root, backup_name)
    manifest_path = os.path.join(backup_dir, "manifest.json")

    if not os.path.exists(manifest_path):
        print("  manifest.json not found in backup.")
        return

    manifest = load_json(manifest_path)
    files = manifest.get("files", [])
    missing = []
    present = 0

    for rel_path in files:
        full_path = os.path.join(backup_dir, rel_path)
        if os.path.exists(full_path):
            present += 1
        else:
            missing.append(rel_path)

    print(f"\n  Project: {manifest.get('project_key', '?')}")
    print(f"  Created: {manifest.get('created_at', '?')}")
    print(f"  Files present: {present}/{len(files)}")

    if missing:
        print(f"  MISSING files ({len(missing)}):")
        for f in missing[:20]:
            print(f"    - {f}")
        if len(missing) > 20:
            print(f"    ... and {len(missing) - 20} more")
    else:
        print("  All files present. Backup is intact.")


def _menu_upload_attachments(config: JiraConfig) -> None:
    """Standalone attachment upload."""
    print("\n--- Upload Attachments Only ---")

    backups = _list_backup_dirs(config.backup_root)
    if not backups:
        print("  No backups found.")
        return

    print("  Available backups:")
    for i, (name, info) in enumerate(backups, 1):
        print(f"    {i}) {name}  ({info})")

    pick = input("\n  Select backup number: ").strip()
    try:
        idx = int(pick) - 1
        backup_name, _ = backups[idx]
    except (ValueError, IndexError):
        print("  Invalid selection.")
        return

    backup_dir = os.path.join(config.backup_root, backup_name)

    target_key = input(
        "  Target project key in Cloud: ",
    ).strip().upper()
    if not target_key:
        print("  No project key entered. Cancelled.")
        return

    dry_run_input = input(
        "  Dry run? (y/n) [n]: ",
    ).strip().lower()
    dry_run = dry_run_input == "y"

    confirm = input("  Proceed? (y/n): ").strip().lower()
    if confirm != "y":
        print("  Cancelled.")
        return

    session = build_session(config)
    client = JiraClient(session, config.jira_url, config)
    uploader = AttachmentUploader(client, config)

    uploader.upload_from_backup(
        backup_dir, target_key, dry_run=dry_run,
    )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _list_backup_dirs(
    backup_root: str,
) -> list[tuple[str, str]]:
    """List backup directories with summary info.

    Returns:
        List of (dir_name, summary_string) tuples.
    """
    if not os.path.isdir(backup_root):
        return []

    results: list[tuple[str, str]] = []
    for name in sorted(os.listdir(backup_root), reverse=True):
        path = os.path.join(backup_root, name)
        if not os.path.isdir(path):
            continue

        # Try to read manifest for summary
        manifest_path = os.path.join(path, "manifest.json")
        if os.path.exists(manifest_path):
            try:
                manifest = load_json(manifest_path)
                info = (
                    f"project={manifest.get('project_key', '?')}, "
                    f"files={len(manifest.get('files', []))}, "
                    f"date={manifest.get('created_at', '?')[:10]}"
                )
            except Exception:
                info = "manifest unreadable"
        else:
            info = "no manifest"

        results.append((name, info))

    return results


def _ask_phases() -> dict[str, bool]:
    """Ask user which restore phases to run.

    Returns:
        Dict of phase name -> enabled.
    """
    print("\n  Restore phases:")
    print("    1) Create issues")
    print("    2) Restore links")
    print("    3) Restore comments")
    print("    4) Restore worklogs")
    print("    5) Upload attachments")
    print("    A) All phases (default)")

    choice = input(
        "  Enter phases to run (e.g. 1,2,3 or A): ",
    ).strip().upper()

    if not choice or choice == "A":
        return {
            "issues": True,
            "links": True,
            "comments": True,
            "worklogs": True,
            "attachments": True,
        }

    selected = {c.strip() for c in choice.split(",")}
    return {
        "issues": "1" in selected,
        "links": "2" in selected,
        "comments": "3" in selected,
        "worklogs": "4" in selected,
        "attachments": "5" in selected,
    }
