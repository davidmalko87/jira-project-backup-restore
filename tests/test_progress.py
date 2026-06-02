# tests/test_progress.py — Resumability and key-mapping tracker
# Author: David Malko

"""Offline tests for ProgressTracker: key mapping, phases, items, dry-run."""

from jira_tool.progress import ProgressTracker


def test_key_mapping(tmp_path):
    p = ProgressTracker(str(tmp_path))
    assert p.get_cloud_key("OLD-1") is None
    assert not p.is_issue_created("OLD-1")

    p.map_key("OLD-1", "NEW-1")
    assert p.get_cloud_key("OLD-1") == "NEW-1"
    assert p.is_issue_created("OLD-1")


def test_key_mapping_persists(tmp_path):
    p1 = ProgressTracker(str(tmp_path))
    p1.map_key("OLD-1", "NEW-1")

    # New tracker on the same dir should reload the mapping.
    p2 = ProgressTracker(str(tmp_path))
    assert p2.get_cloud_key("OLD-1") == "NEW-1"


def test_phase_completion(tmp_path):
    p = ProgressTracker(str(tmp_path))
    assert not p.is_phase_complete("issues")
    p.mark_phase_complete("issues")
    assert p.is_phase_complete("issues")


def test_item_tracking(tmp_path):
    p = ProgressTracker(str(tmp_path))
    assert not p.is_item_done("links", "L1")
    p.mark_item_done("links", "L1")
    assert p.is_item_done("links", "L1")
    # Different phase, same id is independent.
    assert not p.is_item_done("comments", "L1")


def test_user_cache(tmp_path):
    p = ProgressTracker(str(tmp_path))
    found, acct = p.get_cached_user("e@x.com")
    assert found is False and acct is None

    p.cache_user("e@x.com", "acct-123")
    found, acct = p.get_cached_user("e@x.com")
    assert found is True and acct == "acct-123"

    # A cached "not found" (None) is still a cache hit.
    p.cache_user("missing@x.com", None)
    found, acct = p.get_cached_user("missing@x.com")
    assert found is True and acct is None


def test_dry_run_does_not_persist(tmp_path):
    p = ProgressTracker(str(tmp_path), dry_run=True)
    p.map_key("OLD-1", "NEW-1")
    p.mark_phase_complete("issues")

    # Nothing should have been written to disk in dry-run mode.
    assert not (tmp_path / "key_mapping.json").exists()
    assert not (tmp_path / "restore_progress.json").exists()
