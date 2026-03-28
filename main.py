#!/usr/bin/env python3
# main.py — Entry point for Jira Backup & Restore Tool (repo clone usage)
# Author: David Malko

"""Jira Backup & Restore Tool.

Usage:
    python main.py                      # Interactive menu
    python main.py --backup KEY         # Backup a project (non-interactive)
    python main.py --backup KEY1,KEY2   # Backup multiple projects
    python main.py --restore DIR --target KEY  # Restore (non-interactive)
    python main.py --restore DIR --target KEY --dry-run
"""

from jira_tool.cli import main

if __name__ == "__main__":
    main()
