# tests/test_restore_ordering.py — Issue creation ordering & phase sequence
# Author: David Malko

"""Offline tests for the two-pass epic->regular->subtask ordering and the
default restore phase set."""

from jira_tool.restore import _is_subtask, _issue_sort_key


def _issue(itype):
    return {"key": "X-1", "fields": {"issuetype": {"name": itype}}}


def test_sort_key_order():
    assert _issue_sort_key(_issue("Epic")) == 0
    assert _issue_sort_key(_issue("Task")) == 1
    assert _issue_sort_key(_issue("Story")) == 1
    assert _issue_sort_key(_issue("Sub-task")) == 2
    assert _issue_sort_key(_issue("Subtask")) == 2


def test_sorted_puts_epics_first_subtasks_last():
    issues = [
        _issue("Sub-task"),
        _issue("Task"),
        _issue("Epic"),
    ]
    ordered = sorted(issues, key=_issue_sort_key)
    names = [i["fields"]["issuetype"]["name"] for i in ordered]
    assert names == ["Epic", "Task", "Sub-task"]


def test_is_subtask():
    assert _is_subtask(_issue("Sub-task"))
    assert _is_subtask(_issue("Subtask"))
    assert not _is_subtask(_issue("Task"))
    assert not _is_subtask(_issue("Epic"))


def test_helpers_tolerate_missing_fields():
    assert _issue_sort_key({}) == 1
    assert _issue_sort_key({"fields": {}}) == 1
    assert _issue_sort_key({"fields": {"issuetype": None}}) == 1
    assert _is_subtask({}) is False


def test_two_pass_simulation():
    """Simulate the two-pass loop: every parent must be created before any
    sub-task that depends on it."""
    issues = [
        {"key": "P-3", "fields": {"issuetype": {"name": "Sub-task"},
                                  "parent": {"key": "P-1"}}},
        {"key": "P-1", "fields": {"issuetype": {"name": "Task"}}},
        {"key": "P-2", "fields": {"issuetype": {"name": "Epic"}}},
    ]
    created_order = []
    for pass_num in (0, 1):
        for issue in sorted(issues, key=_issue_sort_key):
            if pass_num == 0 and _is_subtask(issue):
                continue
            if pass_num == 1 and not _is_subtask(issue):
                continue
            created_order.append(issue["key"])

    # Parent P-1 created before sub-task P-3.
    assert created_order.index("P-1") < created_order.index("P-3")
    # Epic created in the first pass.
    assert created_order[0] == "P-2"
