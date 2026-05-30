"""todo-mcp-server entry point.

MCP server exposing todo CRUD + search as Tools, several list views and an
aggregate stats view as Resources (including URI-templated resources), and
weekly_review / daily_plan Prompts. A read/write HTTP dashboard runs alongside
in a daemon thread.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from todo_mcp import dashboard, data

mcp = FastMCP("todo")

# Populated by main(). Tool/Resource/Prompt callbacks read from here.
# Accessing them before main() runs raises KeyError — intentional: the server
# has no business serving requests before --project-root is resolved.
_state: dict = {}


def _todos_path() -> Path:
    return _state["project_root"] / ".claude" / "todos.md"


# ---------- Tools (writes + search) ----------

@mcp.tool()
def add_todo(
    text: str,
    priority: str = "med",
    due: str | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Add a new todo to the project's todo list.

    Args:
        text: The todo content. Required, non-empty.
        priority: One of "high", "med", "low". Defaults to "med".
        due: Due date as YYYY-MM-DD, or null/omitted for no due date.
        tags: Optional list of tags (lowercase letters/digits/_/-, no spaces).

    Returns:
        The created todo (dict with id, done, prio, due, tags, text).
    """
    return data.add(_todos_path(), text, priority=priority, due=due, tags=tags)


@mcp.tool()
def mark_done(id: int) -> dict:
    """Mark the todo with the given id as done. Returns the updated todo."""
    return data.mark_done(_todos_path(), id, done=True)


@mcp.tool()
def edit_todo(
    id: int,
    text: str | None = None,
    priority: str | None = None,
    due: str | None = None,
    done: bool | None = None,
    tags: list[str] | None = None,
) -> dict:
    """Edit fields of an existing todo. Pass only the fields you want to change.

    Args:
        id: The todo id.
        text: New text. Omit to keep existing.
        priority: New priority (high/med/low). Omit to keep existing.
        due: New due date YYYY-MM-DD; pass empty string to clear an existing date.
        done: True/False to set status. Use this to "undo" a completed todo.
        tags: New full tag list (replaces existing). Pass [] to clear all tags;
              omit to keep existing tags.

    Returns:
        The updated todo.
    """
    return data.edit(
        _todos_path(),
        id,
        text=text,
        priority=priority,
        due=due,
        done=done,
        tags=tags,
    )


@mcp.tool()
def remove_todo(id: int) -> dict:
    """Remove the todo with the given id. Returns the removed todo."""
    return data.remove(_todos_path(), id)


@mcp.tool()
def search_todos(
    query: str | None = None,
    tag: str | None = None,
    priority: str | None = None,
    status: str = "all",
    due_before: str | None = None,
    due_after: str | None = None,
) -> list[dict]:
    """Search todos by any combination of criteria (all conditions AND together).

    Args:
        query: Case-insensitive substring to match in the todo text.
        tag: Return only todos carrying this tag.
        priority: Filter by "high"/"med"/"low".
        status: "open", "done", or "all" (default).
        due_before: Return todos whose due date is strictly before this YYYY-MM-DD.
        due_after: Return todos whose due date is strictly after this YYYY-MM-DD.

    Returns:
        A list of matching todo dicts, sorted by id. Omitted criteria don't filter.
    """
    return data.search(
        _todos_path(),
        query=query,
        tag=tag,
        priority=priority,
        status=status,
        due_before=due_before,
        due_after=due_after,
    )


# ---------- Resources (reads) ----------

@mcp.resource("todo://list", mime_type="text/markdown")
def todos_list() -> str:
    """The full todos.md content as markdown, served as a Resource."""
    path = _todos_path()
    if not path.exists():
        return "# Todos\n\n_(empty — no todos yet)_\n"
    return path.read_text(encoding="utf-8")


@mcp.resource("todo://tag/{tag}", mime_type="text/markdown")
def todos_by_tag(tag: str) -> str:
    """Todos carrying the given tag, rendered as markdown (URI-templated resource)."""
    todos = data.search(_todos_path(), tag=tag)
    return _render_md(todos, header=f"# Todos tagged `{tag}`")


@mcp.resource("todo://status/{status}", mime_type="text/markdown")
def todos_by_status(status: str) -> str:
    """Todos filtered by status: open / done (URI-templated resource)."""
    todos = data.search(_todos_path(), status=status)
    return _render_md(todos, header=f"# {status.capitalize()} todos")


@mcp.resource("todo://stats", mime_type="application/json")
def todos_stats() -> str:
    """Aggregate statistics over the todo list, as JSON."""
    return json.dumps(data.stats(_todos_path()), ensure_ascii=False, indent=2)


def _render_md(todos: list[dict], header: str) -> str:
    if not todos:
        return f"{header}\n\n_(none)_\n"
    lines = [header, ""]
    for t in todos:
        mark = "x" if t["done"] else " "
        due = f" (due: {t['due']})" if t["due"] else ""
        tags = f" (tags: {','.join(t['tags'])})" if t["tags"] else ""
        lines.append(f"- [{mark}] #{t['id']} [{t['prio']}]{due}{tags} {t['text']}")
    return "\n".join(lines) + "\n"


# ---------- Prompts ----------

@mcp.prompt()
def weekly_review() -> str:
    """Generate a prompt for reviewing the past week's todos."""
    contents = _todos_text()
    return (
        "Please do a weekly review of these todos.\n\n"
        "1. List what was completed (status = done).\n"
        "2. List what's still open, sorted by priority.\n"
        "3. Flag any items with a due date that has passed.\n"
        "4. Suggest the top 3 todos to focus on next week.\n\n"
        f"Current todos:\n\n```markdown\n{contents}\n```\n"
    )


@mcp.prompt()
def daily_plan() -> str:
    """Generate a prompt for planning today's work from the open todos + stats."""
    stats = json.dumps(data.stats(_todos_path()), ensure_ascii=False, indent=2)
    contents = _todos_text()
    return (
        "Help me plan today. Using the open todos and stats below:\n\n"
        "1. Call out anything overdue — these need attention first.\n"
        "2. Pick the Top 3 to do today, balancing priority and due dates.\n"
        "3. Note anything due in the next few days I should not forget.\n"
        "Keep it short and actionable.\n\n"
        f"Stats:\n\n```json\n{stats}\n```\n\n"
        f"Todos:\n\n```markdown\n{contents}\n```\n"
    )


def _todos_text() -> str:
    path = _todos_path()
    return path.read_text(encoding="utf-8") if path.exists() else "(no todos.md yet)"


# ---------- Dashboard ----------

@mcp.tool()
def open_dashboard() -> str:
    """Return the URL of the web dashboard for the todo list.

    Opening this URL in a browser shows the todos as an interactive table
    (view / add / edit / complete / delete). The dashboard re-reads the file
    on every request.
    """
    return f"http://localhost:{_state['dashboard_port']}"


# ---------- Entry point ----------

def _resolve_project_root(arg: Path | None) -> Path:
    """--project-root arg > $TODO_MCP_PROJECT_ROOT > current working directory."""
    if arg is not None:
        return arg.resolve()
    env = os.environ.get("TODO_MCP_PROJECT_ROOT")
    if env:
        return Path(env).resolve()
    return Path.cwd().resolve()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="todo-mcp-server",
        description="MCP server exposing a project-local todo list (.claude/todos.md)",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help=(
            "Project root containing .claude/todos.md. "
            "Defaults to $TODO_MCP_PROJECT_ROOT, then the current directory."
        ),
    )
    args = parser.parse_args()

    root = _resolve_project_root(args.project_root)
    if not root.is_dir():
        print(f"error: project-root {root} is not a directory", file=sys.stderr)
        sys.exit(1)
    _state["project_root"] = root

    # Start the HTTP dashboard before entering the MCP loop.
    _state["dashboard_port"] = dashboard.start(_todos_path)

    # All log lines go to stderr — stdout is owned by the MCP stdio transport.
    print(f"[todo-mcp] project-root: {root}", file=sys.stderr)
    print(
        f"[todo-mcp] dashboard:    http://localhost:{_state['dashboard_port']}",
        file=sys.stderr,
    )

    mcp.run()


if __name__ == "__main__":
    main()
