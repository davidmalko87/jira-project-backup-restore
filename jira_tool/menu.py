# menu.py — Interactive CLI menu for Jira Backup & Restore Tool
# Author: David Malko

"""Interactive menu for guided backup, restore, and utility operations."""

import logging
import os
import sys

from jira_tool import __version__
from jira_tool.api_client import JiraApiError, JiraClient
from jira_tool.attachments import AttachmentUploader
from jira_tool.auth import build_session
from jira_tool.backup import BackupManager, validate_backup
from jira_tool.config import JiraConfig
from jira_tool.export import (
    export_backup_to_csv,
    format_size,
    get_backup_statistics,
)
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
        elif choice == "6":
            _menu_export_csv(config)
        elif choice == "7":
            _menu_inspect_backup(config)
        elif choice == "8":
            _menu_test_connection(config)
        elif choice == "9":
            _menu_show_config(config)
        elif choice == "10":
            _menu_cleanup(config)
        elif choice == "0":
            print("\nGoodbye.")
            sys.exit(0)
        else:
            print("\n  Invalid choice. Try again.\n")


def _print_header(config: JiraConfig) -> None:
    """Display the main menu."""
    auth = "API Token" if config.api_token else "Cookie"
    print(f"\n{'=' * 50}")
    print(f"  Jira Backup & Restore Tool v{__version__}")
    print(f"{'=' * 50}")
    print(f"  Instance : {config.jira_url}")
    print(f"  Auth     : {auth}")
    print(f"  Backups  : {config.backup_root}")
    print()
    print("  --- Backup & Restore ---")
    print("  1) Backup project(s)")
    print("  2) Restore project from backup")
    print()
    print("  --- Browse & Analyze ---")
    print("  3) List existing backups")
    print("  4) Validate backup integrity")
    print("  5) Upload attachments only")
    print("  6) Export backup to CSV")
    print("  7) Inspect backup details")
    print()
    print("  --- Settings & Tools ---")
    print("  8) Test Jira connection")
    print("  9) Show current configuration")
    print("  10) Cleanup incomplete backups")
    print("  0) Exit")
    print()


def _pause() -> None:
    """Pause until user presses Enter."""
    print()
    input("  Press Enter to return to menu...")


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

    skip_input = input(
        "  Skip projects with an existing complete backup? (y/n) [y]: ",
    ).strip().lower()
    skip_existing = skip_input != "n"

    confirm = input("  Proceed? (y/n): ").strip().lower()
    if confirm != "y":
        print("  Cancelled.")
        return

    session = build_session(config)
    client = JiraClient(session, config.jira_url, config)
    manager = BackupManager(client, config)

    if len(keys) == 1:
        if skip_existing:
            existing = manager._find_existing_backup(keys[0])
            if existing:
                print(f"  [SKIP] {keys[0]} — backup exists: {existing}")
                _pause()
                return
        backup_dir = manager.backup_project(keys[0])
        _print_backup_summary(backup_dir)
    else:
        results = manager.backup_projects(keys, skip_existing=skip_existing)
        for backup_dir in results:
            _print_backup_summary(backup_dir)

    _pause()


def _menu_restore(config: JiraConfig) -> None:
    """List backups, pick one, and run restore."""
    print("\n--- Restore Project ---")

    backups = _list_backup_dirs(config.backup_root)
    if not backups:
        print("  No backups found.")
        _pause()
        return

    print("  Available backups:")
    for i, (name, info) in enumerate(backups, 1):
        print(f"    {i}) {name}  ({info})")

    pick = input("\n  Select backup number (or 'b' to go back): ").strip()
    if pick.lower() == "b":
        return
    try:
        idx = int(pick) - 1
        backup_name, _ = backups[idx]
    except (ValueError, IndexError):
        print("  Invalid selection.")
        _pause()
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
    enabled = [name for name, on in phases.items() if on]
    print(f"  Phases:  {', '.join(enabled)}")
    confirm = input("  Proceed? (y/n): ").strip().lower()
    if confirm != "y":
        print("  Cancelled.")
        return

    session = build_session(config)
    client = JiraClient(session, config.jira_url, config)
    progress = ProgressTracker(backup_dir, dry_run=dry_run)
    manager = RestoreManager(client, config, progress)

    manager.restore_project(
        backup_dir, target_key,
        dry_run=dry_run, phases=phases,
    )
    _pause()


def _menu_list_backups(config: JiraConfig) -> None:
    """Show existing backups with summary info."""
    print("\n--- Existing Backups ---")

    backups = _list_backup_dirs(config.backup_root)
    if not backups:
        print("  No backups found in:", config.backup_root)
        _pause()
        return

    # Compute total size
    total_size = 0
    for name, info in backups:
        path = os.path.join(config.backup_root, name)
        for root, _, files in os.walk(path):
            for fname in files:
                try:
                    total_size += os.path.getsize(os.path.join(root, fname))
                except OSError:
                    pass

    print(f"  {'No.':<5} {'Backup Name':<35} {'Details'}")
    print(f"  {'-' * 5} {'-' * 35} {'-' * 40}")
    for i, (name, info) in enumerate(backups, 1):
        print(f"  {i:<5} {name:<35} {info}")

    print(f"\n  Total: {len(backups)} backup(s), {format_size(total_size)}")
    _pause()


def _menu_validate_backup(config: JiraConfig) -> None:
    """Check manifest against actual files."""
    print("\n--- Validate Backup ---")

    backups = _list_backup_dirs(config.backup_root)
    if not backups:
        print("  No backups found.")
        _pause()
        return

    print("  Available backups:")
    for i, (name, info) in enumerate(backups, 1):
        print(f"    {i}) {name}  ({info})")

    pick = input("\n  Select backup number (or 'b' to go back): ").strip()
    if pick.lower() == "b":
        return
    try:
        idx = int(pick) - 1
        backup_name, _ = backups[idx]
    except (ValueError, IndexError):
        print("  Invalid selection.")
        _pause()
        return

    backup_dir = os.path.join(config.backup_root, backup_name)
    print("\n  Verifying files and checksums...")
    _print_validation_report(backup_dir)
    _pause()


def _print_validation_report(backup_dir: str) -> None:
    """Run validate_backup and print a human-readable report."""
    result = validate_backup(backup_dir)

    if not result["manifest_found"]:
        print("  manifest.json not found — backup is incomplete.")
        return

    print(f"\n  Project: {result['project_key']}")
    print(f"  Created: {result['created_at']}")

    flag = result["complete_flag"]
    if flag is False:
        print("  Completeness flag: INCOMPLETE (see counts below)")
    elif flag is True:
        print("  Completeness flag: complete")
    else:
        print("  Completeness flag: (legacy backup, not recorded)")

    print(
        f"  Files present : {result['files_present']}/{result['files_total']}"
    )
    print(
        f"  Checksums OK  : {result['checksum_ok']}/{result['checksum_total']}"
    )

    ver = result["verification"]
    if ver.get("issues_expected") is not None:
        print(
            f"  Issues        : {ver.get('issues_actual', 0)} stored / "
            f"~{ver['issues_expected']} reported by Jira"
        )
    if ver.get("attachments_expected") is not None:
        print(
            f"  Attachments   : {ver.get('attachments_actual', 0)} stored / "
            f"{ver['attachments_expected']} referenced"
        )

    missing = result["missing"]
    failed = result["checksum_failed"]
    if missing:
        print(f"\n  MISSING files ({len(missing)}):")
        for f in missing[:20]:
            print(f"    - {f}")
        if len(missing) > 20:
            print(f"    ... and {len(missing) - 20} more")
    if failed:
        print(f"\n  CHECKSUM MISMATCH ({len(failed)}) — files changed/corrupt:")
        for f in failed[:20]:
            print(f"    - {f}")
        if len(failed) > 20:
            print(f"    ... and {len(failed) - 20} more")

    if not missing and not failed and flag is not False:
        print("\n  Backup is intact and complete.")
    elif not missing and not failed:
        print("\n  Files intact, but backup was flagged incomplete at capture.")


def _menu_upload_attachments(config: JiraConfig) -> None:
    """Standalone attachment upload."""
    print("\n--- Upload Attachments Only ---")

    backups = _list_backup_dirs(config.backup_root)
    if not backups:
        print("  No backups found.")
        _pause()
        return

    print("  Available backups:")
    for i, (name, info) in enumerate(backups, 1):
        print(f"    {i}) {name}  ({info})")

    pick = input("\n  Select backup number (or 'b' to go back): ").strip()
    if pick.lower() == "b":
        return
    try:
        idx = int(pick) - 1
        backup_name, _ = backups[idx]
    except (ValueError, IndexError):
        print("  Invalid selection.")
        _pause()
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
    _pause()


def _menu_export_csv(config: JiraConfig) -> None:
    """Export backup data to CSV files."""
    print("\n--- Export Backup to CSV ---")

    backups = _list_backup_dirs(config.backup_root)
    if not backups:
        print("  No backups found.")
        _pause()
        return

    print("  Available backups:")
    for i, (name, info) in enumerate(backups, 1):
        print(f"    {i}) {name}  ({info})")

    pick = input("\n  Select backup number (or 'b' to go back): ").strip()
    if pick.lower() == "b":
        return
    try:
        idx = int(pick) - 1
        backup_name, _ = backups[idx]
    except (ValueError, IndexError):
        print("  Invalid selection.")
        _pause()
        return

    backup_dir = os.path.join(config.backup_root, backup_name)
    default_output = os.path.join(backup_dir, "csv_export")

    output_input = input(
        f"  Output directory [{default_output}]: ",
    ).strip()
    output_dir = output_input if output_input else default_output

    print(f"\n  Source:  {backup_dir}")
    print(f"  Output:  {output_dir}")
    confirm = input("  Proceed? (y/n): ").strip().lower()
    if confirm != "y":
        print("  Cancelled.")
        return

    print("\n  Exporting...")
    results = export_backup_to_csv(backup_dir, output_dir)

    print(f"\n  Export complete! Files written to: {output_dir}")
    print()
    for filename, count in results.items():
        print(f"    {filename:<20} {count:>6} rows")
    print(f"\n  Total: {len(results)} CSV file(s)")
    _pause()


def _menu_inspect_backup(config: JiraConfig) -> None:
    """Show detailed statistics for a backup."""
    print("\n--- Inspect Backup Details ---")

    backups = _list_backup_dirs(config.backup_root)
    if not backups:
        print("  No backups found.")
        _pause()
        return

    print("  Available backups:")
    for i, (name, info) in enumerate(backups, 1):
        print(f"    {i}) {name}  ({info})")

    pick = input("\n  Select backup number (or 'b' to go back): ").strip()
    if pick.lower() == "b":
        return
    try:
        idx = int(pick) - 1
        backup_name, _ = backups[idx]
    except (ValueError, IndexError):
        print("  Invalid selection.")
        _pause()
        return

    backup_dir = os.path.join(config.backup_root, backup_name)
    _print_detailed_stats(backup_dir)
    _pause()


def _menu_test_connection(config: JiraConfig) -> None:
    """Test Jira connectivity and permissions."""
    print("\n--- Test Jira Connection ---")
    print(f"  Connecting to {config.jira_url} ...")

    try:
        session = build_session(config)
        client = JiraClient(session, config.jira_url, config)

        # Test 1: Basic connectivity (myself endpoint)
        print("\n  [1/3] Testing authentication...")
        try:
            myself = client.get("/rest/api/3/myself")
            display_name = myself.get("displayName", "Unknown")
            email = myself.get("emailAddress", "")
            print(f"         Authenticated as: {display_name} ({email})")
        except JiraApiError as exc:
            print(f"         FAILED: {exc}")
            _pause()
            return

        # Test 2: Project access
        print("  [2/3] Testing project access...")
        try:
            projects = client.get(
                "/rest/api/3/project/search",
                params={"maxResults": 5},
            )
            project_list = projects.get("values", [])
            print(f"         Accessible projects: {len(project_list)} shown")
            for p in project_list[:5]:
                print(f"           - {p.get('key', '?')}: {p.get('name', '?')}")
            total = projects.get("total", len(project_list))
            if total > 5:
                print(f"           ... and {total - 5} more")
        except JiraApiError as exc:
            print(f"         Warning: {exc}")

        # Test 3: Server info
        print("  [3/3] Fetching server info...")
        try:
            info = client.get("/rest/api/3/serverInfo")
            print(f"         Server title: {info.get('serverTitle', '?')}")
            print(f"         Version: {info.get('version', '?')}")
            print(f"         Deployment: {info.get('deploymentType', '?')}")
        except JiraApiError:
            print("         Server info not available (non-critical).")

        print("\n  Connection test PASSED.")

    except Exception as exc:
        print(f"\n  Connection test FAILED: {exc}")

    _pause()


def _menu_show_config(config: JiraConfig) -> None:
    """Display current configuration settings."""
    print("\n--- Current Configuration ---")
    auth = "API Token" if config.api_token else "Cookie"
    print("\n  Jira Instance")
    print(f"    URL            : {config.jira_url}")
    print(f"    Email          : {config.email or '(not set)'}")
    print(f"    Auth method    : {auth}")
    print(f"    SSL verify     : {config.verify_ssl}")
    print("\n  Backup Settings")
    print(f"    Backup root    : {os.path.abspath(config.backup_root)}")
    print(f"    Page size      : {config.page_size}")
    print(f"    Max retries    : {config.max_retries}")
    print(f"    Read timeout   : {config.read_timeout}s")
    print(f"    API delay      : {config.api_delay}s")
    print(f"    Chunk size     : {format_size(config.chunk_size)}")
    print("\n  Data Toggles")
    print(f"    Attachments    : {'Enabled' if config.include_attachments else 'Disabled'}")
    print(f"    Changelog      : {'Enabled' if config.include_changelog else 'Disabled'}")
    print(f"    Worklogs       : {'Enabled' if config.include_worklogs else 'Disabled'}")

    if config.legacy_key_jql_template:
        print("\n  Legacy")
        print(f"    JQL template   : {config.legacy_key_jql_template}")

    _pause()


def _menu_cleanup(config: JiraConfig) -> None:
    """List and remove incomplete backup folders (no manifest.json)."""
    print("\n--- Cleanup Incomplete Backups ---")

    root = config.backup_root
    if not os.path.isdir(root):
        print("  Backup folder not found:", root)
        _pause()
        return

    incomplete = [
        name
        for name in sorted(os.listdir(root))
        if os.path.isdir(os.path.join(root, name))
        and not os.path.exists(os.path.join(root, name, "manifest.json"))
    ]

    if not incomplete:
        print("  No incomplete backups found. Nothing to clean up.")
        _pause()
        return

    print(f"  Found {len(incomplete)} incomplete backup folder(s):\n")
    for name in incomplete:
        print(f"    - {name}")

    print()
    confirm = input(
        f"  Delete all {len(incomplete)} incomplete folder(s)? (y/n): "
    ).strip().lower()
    if confirm != "y":
        print("  Cancelled.")
        return

    session = build_session(config)
    client = JiraClient(session, config.jira_url, config)
    manager = BackupManager(client, config)

    removed = manager.cleanup_all_incomplete()
    print(f"\n  Removed {removed} incomplete backup folder(s).")
    _pause()


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
                file_count = len(manifest.get("files", []))

                # Compute directory size
                dir_size = 0
                for root, _, files in os.walk(path):
                    for fname in files:
                        try:
                            dir_size += os.path.getsize(
                                os.path.join(root, fname),
                            )
                        except OSError:
                            pass

                info = (
                    f"project={manifest.get('project_key', '?')}, "
                    f"files={file_count}, "
                    f"size={format_size(dir_size)}, "
                    f"date={manifest.get('created_at', '?')[:10]}"
                )
            except Exception:
                info = "manifest unreadable"
        else:
            info = "incomplete (no manifest)"

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


def _print_backup_summary(backup_dir: str) -> None:
    """Print summary statistics after a backup completes."""
    stats = get_backup_statistics(backup_dir)
    print(f"\n  {'─' * 40}")
    print("  Backup Summary")
    print(f"  {'─' * 40}")
    print(f"    Issues       : {stats['issue_count']}")
    print(f"    Comments     : {stats['comment_count']}")
    print(f"    Attachments  : {stats['attachment_count']}")
    print(f"    Worklogs     : {stats['worklog_count']}")
    print(f"    Components   : {stats['component_count']}")
    print(f"    Versions     : {stats['version_count']}")
    print(f"    Total size   : {format_size(stats['total_size_bytes'])}")

    if stats["type_counts"]:
        print("\n    Issue types:")
        for itype, count in stats["type_counts"].most_common():
            print(f"      {itype:<20} {count:>5}")


def _print_detailed_stats(backup_dir: str) -> None:
    """Print comprehensive backup statistics."""
    # Read manifest
    manifest_path = os.path.join(backup_dir, "manifest.json")
    if os.path.exists(manifest_path):
        manifest = load_json(manifest_path)
        print(f"\n  Project     : {manifest.get('project_key', '?')}")
        print(f"  Source      : {manifest.get('source_url', '?')}")
        print(f"  Created     : {manifest.get('created_at', '?')}")
        print(f"  Tool version: {manifest.get('tool_version', '?')}")
    else:
        print("\n  WARNING: No manifest.json — backup may be incomplete.")

    stats = get_backup_statistics(backup_dir)

    print(f"\n  {'─' * 45}")
    print("  Overview")
    print(f"  {'─' * 45}")
    print(f"    Total issues     : {stats['issue_count']}")
    print(f"    Total comments   : {stats['comment_count']}")
    print(f"    Total attachments: {stats['attachment_count']}")
    print(f"    Total worklogs   : {stats['worklog_count']}")
    print(f"    Components       : {stats['component_count']}")
    print(f"    Versions         : {stats['version_count']}")
    print(f"    Disk size        : {format_size(stats['total_size_bytes'])}")

    if stats["type_counts"]:
        print(f"\n  {'─' * 45}")
        print("  Issue Types")
        print(f"  {'─' * 45}")
        for itype, count in stats["type_counts"].most_common():
            bar = "#" * min(count, 30)
            print(f"    {itype:<20} {count:>5}  {bar}")

    if stats["status_counts"]:
        print(f"\n  {'─' * 45}")
        print("  Issue Statuses")
        print(f"  {'─' * 45}")
        for status, count in stats["status_counts"].most_common():
            bar = "#" * min(count, 30)
            print(f"    {status:<20} {count:>5}  {bar}")

    if stats["priority_counts"]:
        print(f"\n  {'─' * 45}")
        print("  Priorities")
        print(f"  {'─' * 45}")
        for priority, count in stats["priority_counts"].most_common():
            print(f"    {priority:<20} {count:>5}")

    if stats["assignees"]:
        print(f"\n  {'─' * 45}")
        print("  Top Assignees")
        print(f"  {'─' * 45}")
        for assignee, count in stats["assignees"].most_common(10):
            print(f"    {assignee:<30} {count:>5}")
