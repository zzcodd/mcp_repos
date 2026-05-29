"""Tests for search_todos and stats (todo_mcp.data.search / .stats)."""
from __future__ import annotations

from datetime import date

import pytest

from todo_mcp import data


@pytest.fixture
def populated(tmp_path):
    f = tmp_path / ".claude" / "todos.md"
    data.add(f, "buy milk", priority="low", tags=["home"])
    data.add(f, "write agent spec", priority="high", due="2026-06-01",
             tags=["agent", "work"])
    data.add(f, "review MCP code", priority="med", due="2026-05-20",
             tags=["work"])
    data.mark_done(f, 3, done=True)  # #3 done, overdue relative to 2026-05-30
    return f


# ---------- search ----------

def test_search_no_filters_returns_all(populated):
    assert len(data.search(populated)) == 3


def test_search_by_status(populated):
    assert {t["id"] for t in data.search(populated, status="open")} == {1, 2}
    assert {t["id"] for t in data.search(populated, status="done")} == {3}


def test_search_by_priority(populated):
    assert {t["id"] for t in data.search(populated, priority="high")} == {2}


def test_search_by_tag(populated):
    assert {t["id"] for t in data.search(populated, tag="work")} == {2, 3}
    assert {t["id"] for t in data.search(populated, tag="home")} == {1}


def test_search_by_query_substring_case_insensitive(populated):
    assert {t["id"] for t in data.search(populated, query="AGENT")} == {2}


def test_search_due_before_and_after(populated):
    assert {t["id"] for t in data.search(populated, due_before="2026-05-25")} == {3}
    assert {t["id"] for t in data.search(populated, due_after="2026-05-25")} == {2}


def test_search_combined_criteria_are_anded(populated):
    # work-tagged AND open -> only #2 (#3 is done)
    res = data.search(populated, tag="work", status="open")
    assert {t["id"] for t in res} == {2}


def test_search_invalid_status_raises(populated):
    with pytest.raises(ValueError):
        data.search(populated, status="bogus")


# ---------- stats ----------

def test_stats_counts_and_rate(populated):
    s = data.stats(populated, today=date(2026, 5, 30))
    assert s["total"] == 3
    assert s["done"] == 1
    assert s["open"] == 2
    assert s["completion_rate"] == 0.33


def test_stats_by_priority_counts_open_only(populated):
    s = data.stats(populated, today=date(2026, 5, 30))
    # open: #1 low, #2 high  (#3 med is done -> excluded)
    assert s["by_priority"] == {"high": 1, "med": 0, "low": 1}


def test_stats_by_tag_counts_open_only(populated):
    s = data.stats(populated, today=date(2026, 5, 30))
    # open tags: #1 home, #2 agent+work
    assert s["by_tag"] == {"home": 1, "agent": 1, "work": 1}


def test_stats_overdue_and_due_soon(populated):
    # #2 due 2026-06-01 is within 7 days of 2026-05-30 -> due_soon
    s = data.stats(populated, today=date(2026, 5, 30))
    assert s["due_next_7_days"] == 1
    assert s["overdue"] == 0  # the only overdue item (#3) is done, excluded


def test_stats_overdue_open_item(tmp_path):
    f = tmp_path / ".claude" / "todos.md"
    data.add(f, "late", priority="high", due="2026-01-01")
    s = data.stats(f, today=date(2026, 5, 30))
    assert s["overdue"] == 1


def test_stats_empty(tmp_path):
    f = tmp_path / ".claude" / "todos.md"
    s = data.stats(f, today=date(2026, 5, 30))
    assert s["total"] == 0
    assert s["completion_rate"] == 0.0
