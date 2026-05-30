"""Tests for the todos.md read/write layer (todo_mcp.data)."""
from __future__ import annotations

import pytest

from todo_mcp import data


@pytest.fixture
def todos_file(tmp_path):
    return tmp_path / ".claude" / "todos.md"


# ---------- round-trip ----------

def test_add_then_load_roundtrip(todos_file):
    data.add(todos_file, "write spec", priority="high", due="2026-06-01")
    todos = data.load(todos_file)
    assert len(todos) == 1
    t = todos[0]
    assert t["id"] == 1
    assert t["text"] == "write spec"
    assert t["prio"] == "high"
    assert t["due"] == "2026-06-01"
    assert t["done"] is False
    assert t["tags"] == []


def test_roundtrip_with_tags_and_due(todos_file):
    data.add(todos_file, "ship it", priority="med", due="2026-07-01",
             tags=["agent", "learning"])
    (t,) = data.load(todos_file)
    assert t["tags"] == ["agent", "learning"]
    assert t["due"] == "2026-07-01"


def test_roundtrip_tags_without_due(todos_file):
    data.add(todos_file, "no due", tags=["chore"])
    (t,) = data.load(todos_file)
    assert t["due"] is None
    assert t["tags"] == ["chore"]


def test_empty_file_loads_empty(todos_file):
    assert data.load(todos_file) == []


# ---------- backward compatibility (v0.1 format, no tags) ----------

def test_parses_legacy_v01_lines(todos_file):
    """Lines written by the old (pre-tags) format must still parse."""
    todos_file.parent.mkdir(parents=True)
    todos_file.write_text(
        "# Todos\n\n"
        "<!-- Format: - [ ] #ID [priority] (due: YYYY-MM-DD) text -->\n\n"
        "- [x] #1 [high] (due: 2026-05-30) finish skill\n"
        "- [ ] #2 [low] test list\n",
        encoding="utf-8",
    )
    todos = data.load(todos_file)
    assert len(todos) == 2
    assert todos[0]["done"] is True
    assert todos[0]["tags"] == []
    assert todos[1]["text"] == "test list"
    assert todos[1]["due"] is None


def test_unparseable_lines_ignored(todos_file):
    todos_file.parent.mkdir(parents=True)
    todos_file.write_text(
        "# Todos\n\nsome free text note\n"
        "- [ ] #1 [med] real todo\n"
        "- not a todo line\n",
        encoding="utf-8",
    )
    todos = data.load(todos_file)
    assert len(todos) == 1
    assert todos[0]["text"] == "real todo"


# ---------- tag normalization ----------

def test_tag_normalization_lowercase_strip_dedupe(todos_file):
    data.add(todos_file, "x", tags=["  Agent ", "AGENT", "learning"])
    (t,) = data.load(todos_file)
    assert t["tags"] == ["agent", "learning"]


def test_tags_accepts_comma_string(todos_file):
    data.add(todos_file, "x", tags="a, b ,c")
    (t,) = data.load(todos_file)
    assert t["tags"] == ["a", "b", "c"]


def test_empty_tag_entries_dropped(todos_file):
    data.add(todos_file, "x", tags=["", "  ", "real"])
    (t,) = data.load(todos_file)
    assert t["tags"] == ["real"]


@pytest.mark.parametrize("bad", ["has space", "comma,tag", "paren)", "UP!"])
def test_invalid_tag_chars_rejected(todos_file, bad):
    with pytest.raises(ValueError):
        data.add(todos_file, "x", tags=[bad])


# ---------- ids ----------

def test_ids_increment_and_never_reused(todos_file):
    data.add(todos_file, "a")
    data.add(todos_file, "b")
    data.remove(todos_file, 1)
    third = data.add(todos_file, "c")
    assert third["id"] == 3  # max+1, not reusing the freed #1


# ---------- edit ----------

def test_edit_partial_fields(todos_file):
    data.add(todos_file, "old", priority="low")
    data.edit(todos_file, 1, text="new", priority="high")
    (t,) = data.load(todos_file)
    assert t["text"] == "new"
    assert t["prio"] == "high"


def test_edit_clears_due_with_empty_string(todos_file):
    data.add(todos_file, "x", due="2026-01-01")
    data.edit(todos_file, 1, due="")
    (t,) = data.load(todos_file)
    assert t["due"] is None


def test_edit_replaces_tags(todos_file):
    data.add(todos_file, "x", tags=["old1", "old2"])
    data.edit(todos_file, 1, tags=["new"])
    (t,) = data.load(todos_file)
    assert t["tags"] == ["new"]


def test_edit_clears_tags_with_empty_list(todos_file):
    data.add(todos_file, "x", tags=["a"])
    data.edit(todos_file, 1, tags=[])
    (t,) = data.load(todos_file)
    assert t["tags"] == []


def test_edit_none_tags_keeps_existing(todos_file):
    data.add(todos_file, "x", tags=["keep"])
    data.edit(todos_file, 1, text="changed")  # tags not passed
    (t,) = data.load(todos_file)
    assert t["tags"] == ["keep"]


# ---------- mark_done ----------

def test_mark_done_and_undone(todos_file):
    data.add(todos_file, "x")
    data.mark_done(todos_file, 1, done=True)
    assert data.load(todos_file)[0]["done"] is True
    data.mark_done(todos_file, 1, done=False)
    assert data.load(todos_file)[0]["done"] is False


# ---------- errors ----------

def test_add_invalid_priority(todos_file):
    with pytest.raises(ValueError):
        data.add(todos_file, "x", priority="urgent")


def test_mark_done_missing_id(todos_file):
    data.add(todos_file, "x")
    with pytest.raises(ValueError):
        data.mark_done(todos_file, 999)


def test_remove_missing_id(todos_file):
    with pytest.raises(ValueError):
        data.remove(todos_file, 1)
