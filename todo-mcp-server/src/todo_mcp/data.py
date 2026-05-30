"""Read/write the shared .claude/todos.md file.

The on-disk format is intentionally identical to the todo-manager Skill's
scripts/todo.py, so the Skill and this MCP server can coexist on the same
file without trampling each other. See docs/FORMAT.md for the canonical spec.

Line grammar:
    - [STATUS] #ID [PRIORITY] (due: YYYY-MM-DD)? (tags: tag1,tag2)? TEXT
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from pathlib import Path

PRIORITIES: tuple[str, ...] = ("high", "med", "low")

# Tags: lowercase, [a-z0-9_-]. No commas (the separator) or parens (would
# break the line grammar) allowed inside a tag.
_TAG_RE = re.compile(r"^[a-z0-9_-]+$")

_LINE_RE = re.compile(
    r"^- \[(?P<done>[ x])\] #(?P<id>\d+) \[(?P<prio>high|med|low)\]"
    r"(?: \(due: (?P<due>\d{4}-\d{2}-\d{2})\))?"
    r"(?: \(tags: (?P<tags>[^)]*)\))?"
    r" (?P<text>.+)$"
)

Todo = dict  # alias used for documentation only


# ---------- tag helpers ----------

def normalize_tags(tags: list[str] | str | None) -> list[str]:
    """Clean user-supplied tags: lowercase, strip, dedupe (order-preserving).

    Accepts a list, a comma-separated string, or None (-> []).
    Raises ValueError on a tag containing anything outside [a-z0-9_-].
    """
    if tags is None:
        return []
    if isinstance(tags, str):
        tags = tags.split(",")
    out: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        t = raw.strip().lower()
        if not t:
            continue
        if not _TAG_RE.match(t):
            raise ValueError(
                f"invalid tag {raw!r}: tags must match [a-z0-9_-]+ (no spaces, commas, parens)"
            )
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _parse_tags(raw: str | None) -> list[str]:
    """Lenient parse of the on-disk tags segment (trusts the file)."""
    if not raw:
        return []
    return [s for s in raw.split(",") if s]


# ---------- load / dump ----------

def load(path: Path) -> list[Todo]:
    """Return all parseable todos from the file. Lines that don't match are skipped."""
    if not path.exists():
        return []
    todos: list[Todo] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = _LINE_RE.match(line)
        if not m:
            continue
        todos.append({
            "id": int(m["id"]),
            "done": m["done"] == "x",
            "prio": m["prio"],
            "due": m["due"],
            "tags": _parse_tags(m["tags"]),
            "text": m["text"],
        })
    return todos


def _format_line(t: Todo) -> str:
    mark = "x" if t["done"] else " "
    due = f" (due: {t['due']})" if t.get("due") else ""
    tags = f" (tags: {','.join(t['tags'])})" if t.get("tags") else ""
    return f"- [{mark}] #{t['id']} [{t['prio']}]{due}{tags} {t['text']}"


def dump(path: Path, todos: list[Todo]) -> None:
    """Write the full list back. Header (title + format comment) is regenerated."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Todos",
        "",
        "<!-- Format: - [ ] #ID [priority] (due: YYYY-MM-DD) (tags: a,b) text -->",
        "",
    ]
    for t in sorted(todos, key=lambda x: x["id"]):
        lines.append(_format_line(t))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------- mutations ----------

def add(
    path: Path,
    text: str,
    priority: str = "med",
    due: str | None = None,
    tags: list[str] | str | None = None,
) -> Todo:
    if priority not in PRIORITIES:
        raise ValueError(f"priority must be one of {PRIORITIES}, got {priority!r}")
    todos = load(path)
    new_id = max((t["id"] for t in todos), default=0) + 1
    todo: Todo = {
        "id": new_id,
        "done": False,
        "prio": priority,
        "due": due,
        "tags": normalize_tags(tags),
        "text": text,
    }
    todos.append(todo)
    dump(path, todos)
    return todo


def mark_done(path: Path, todo_id: int, done: bool = True) -> Todo:
    todos = load(path)
    for t in todos:
        if t["id"] == todo_id:
            t["done"] = done
            dump(path, todos)
            return t
    raise ValueError(f"No todo with id #{todo_id}")


def edit(
    path: Path,
    todo_id: int,
    *,
    text: str | None = None,
    priority: str | None = None,
    due: str | None = None,
    done: bool | None = None,
    tags: list[str] | str | None = None,
) -> Todo:
    if priority is not None and priority not in PRIORITIES:
        raise ValueError(f"priority must be one of {PRIORITIES}, got {priority!r}")
    todos = load(path)
    for t in todos:
        if t["id"] == todo_id:
            if text is not None:
                t["text"] = text
            if priority is not None:
                t["prio"] = priority
            if due is not None:
                t["due"] = due or None
            if done is not None:
                t["done"] = done
            if tags is not None:
                t["tags"] = normalize_tags(tags)
            dump(path, todos)
            return t
    raise ValueError(f"No todo with id #{todo_id}")


def remove(path: Path, todo_id: int) -> Todo:
    todos = load(path)
    for i, t in enumerate(todos):
        if t["id"] == todo_id:
            removed = todos.pop(i)
            dump(path, todos)
            return removed
    raise ValueError(f"No todo with id #{todo_id}")


# ---------- query / stats (read-only, derived) ----------

def search(
    path: Path,
    *,
    query: str | None = None,
    tag: str | None = None,
    priority: str | None = None,
    status: str = "all",
    due_before: str | None = None,
    due_after: str | None = None,
) -> list[Todo]:
    """Return todos matching ALL given criteria (omitted criteria don't filter)."""
    if status not in ("open", "done", "all"):
        raise ValueError(f"status must be open/done/all, got {status!r}")
    if priority is not None and priority not in PRIORITIES:
        raise ValueError(f"priority must be one of {PRIORITIES}, got {priority!r}")

    out = load(path)
    if status == "open":
        out = [t for t in out if not t["done"]]
    elif status == "done":
        out = [t for t in out if t["done"]]
    if priority is not None:
        out = [t for t in out if t["prio"] == priority]
    if query:
        q = query.lower()
        out = [t for t in out if q in t["text"].lower()]
    if tag is not None:
        want = tag.strip().lower()
        out = [t for t in out if want in t["tags"]]
    if due_before is not None:
        out = [t for t in out if t["due"] and t["due"] < due_before]
    if due_after is not None:
        out = [t for t in out if t["due"] and t["due"] > due_after]
    return sorted(out, key=lambda x: x["id"])


def stats(path: Path, today: date | None = None) -> dict:
    """Compute aggregate stats. `today` is injectable for deterministic tests."""
    today = today or date.today()
    todos = load(path)
    total = len(todos)
    done = sum(1 for t in todos if t["done"])
    open_todos = [t for t in todos if not t["done"]]

    by_priority: dict[str, int] = {p: 0 for p in PRIORITIES}
    by_tag: dict[str, int] = {}
    for t in open_todos:
        by_priority[t["prio"]] += 1
        for tag in t["tags"]:
            by_tag[tag] = by_tag.get(tag, 0) + 1

    overdue = 0
    due_next_7 = 0
    week_ahead = today + timedelta(days=7)
    for t in open_todos:
        if not t["due"]:
            continue
        d = datetime.strptime(t["due"], "%Y-%m-%d").date()
        if d < today:
            overdue += 1
        elif today <= d <= week_ahead:
            due_next_7 += 1

    return {
        "total": total,
        "open": len(open_todos),
        "done": done,
        "completion_rate": round(done / total, 2) if total else 0.0,
        "by_priority": by_priority,
        "by_tag": by_tag,
        "overdue": overdue,
        "due_next_7_days": due_next_7,
        "generated_at": today.isoformat(),
    }
