"""Smoke tests for the HTTP dashboard API (todo_mcp.dashboard)."""
from __future__ import annotations

import json
import urllib.request

import pytest

from todo_mcp import dashboard, data


@pytest.fixture
def server(tmp_path):
    """Start the dashboard against a temp todos file; yield its base URL."""
    todos_file = tmp_path / ".claude" / "todos.md"
    port = dashboard.start(lambda: todos_file, port=0)  # ephemeral port per test
    yield f"http://127.0.0.1:{port}", todos_file
    # daemon thread dies with the test process; nothing to tear down explicitly.


def _req(method, url, body=None):
    data_bytes = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data_bytes, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode())


def test_index_served(server):
    base, _ = server
    with urllib.request.urlopen(base + "/") as resp:
        assert resp.status == 200
        assert "Todos" in resp.read().decode()


def test_add_with_tags_then_list(server):
    base, _ = server
    _, created = _req("POST", base + "/api/add",
                      {"text": "ship", "priority": "high", "tags": "agent,work"})
    assert created["todo"]["tags"] == ["agent", "work"]

    _, listed = _req("GET", base + "/api/todos")
    assert len(listed["todos"]) == 1
    assert listed["todos"][0]["tags"] == ["agent", "work"]


def test_edit_tags_and_clear(server):
    base, _ = server
    _req("POST", base + "/api/add", {"text": "x", "tags": "a,b"})
    _, edited = _req("POST", base + "/api/edit", {"id": 1, "tags": ""})
    assert edited["todo"]["tags"] == []


def test_toggle_and_delete(server):
    base, _ = server
    _req("POST", base + "/api/add", {"text": "x"})
    _, toggled = _req("POST", base + "/api/toggle", {"id": 1, "done": True})
    assert toggled["todo"]["done"] is True
    _, deleted = _req("POST", base + "/api/delete", {"id": 1})
    assert deleted["todo"]["id"] == 1


def test_dashboard_and_data_share_file(server):
    """A mutation via the API is visible through the data layer (same file)."""
    base, todos_file = server
    _req("POST", base + "/api/add", {"text": "shared", "tags": "x"})
    todos = data.load(todos_file)
    assert todos[0]["text"] == "shared"
    assert todos[0]["tags"] == ["x"]
