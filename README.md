# todo-mcp-server

An [MCP](https://modelcontextprotocol.io) server for a plaintext todo list.
It exposes a project-local `.claude/todos.md` through MCP **Tools** (create /
edit / complete / delete / **search**), **Resources** (list views + aggregate
**stats**, including URI-templated views), and **Prompts** (weekly review /
daily plan) — plus a built-in browser dashboard for visual editing.

The on-disk format is plain, human-readable Markdown, so your todos stay
readable and version-controllable without this tool.

## Install & run

Zero-install with [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uvx todo-mcp-server --project-root /path/to/your/project
```

Or install from PyPI:

```bash
pip install todo-mcp-server
todo-mcp-server --project-root /path/to/your/project
```

The server speaks MCP over **stdio** — it is normally launched by an MCP
client (Claude Code, Cursor, …), not run by hand.

`--project-root` is optional; resolution order is:
`--project-root` > `$TODO_MCP_PROJECT_ROOT` > current working directory.
Todos live in `<project-root>/.claude/todos.md`.

## Register with Claude Code

```bash
claude mcp add todo -s user -- uvx todo-mcp-server --project-root /path/to/your/project
```

Or, in any MCP client config (`mcpServers`):

```jsonc
{
  "mcpServers": {
    "todo": {
      "command": "uvx",
      "args": ["todo-mcp-server", "--project-root", "/path/to/your/project"]
    }
  }
}
```

## Capabilities

### Tools (`tools/call`)

| Tool | Signature | Purpose |
|------|-----------|---------|
| `add_todo` | `(text, priority="med", due=None, tags=None)` | Create a todo |
| `mark_done` | `(id)` | Mark complete |
| `edit_todo` | `(id, text?, priority?, due?, done?, tags?)` | Edit fields (`done=False` to reopen; `tags=[]` to clear) |
| `remove_todo` | `(id)` | Delete |
| `search_todos` | `(query?, tag?, priority?, status="all", due_before?, due_after?)` | Filter by any combination of criteria |
| `open_dashboard` | `()` | Get the dashboard URL |

### Resources (`resources/read`)

| URI | Type | Content |
|-----|------|---------|
| `todo://list` | markdown | Full `todos.md` |
| `todo://tag/{tag}` | markdown | Todos carrying a tag (URI template) |
| `todo://status/{status}` | markdown | `open` / `done` view (URI template) |
| `todo://stats` | json | Counts, completion rate, by-priority/by-tag, overdue, due-soon |

### Prompts (`prompts/get`)

| Prompt | Purpose |
|--------|---------|
| `weekly_review` | Review the week: done / open / overdue + next-week focus |
| `daily_plan` | Plan today: surface overdue, pick a Top-3 from open items |

## Browser dashboard

On startup the server runs a small HTTP dashboard in a daemon thread
(default `http://localhost:8765`, falling back to the next free port). It
renders todos as an interactive table — view, add, edit, complete, tag, and
delete — and re-reads the file on every request. Call `open_dashboard` to get
the URL.

> Bound to `127.0.0.1` only, no auth — intended for local personal use; don't
> expose the port. The dashboard lives and dies with the server process.

## Data format

Each todo is one Markdown line under `<project-root>/.claude/todos.md`:

```
- [ ] #12 [high] (due: 2026-06-01) (tags: agent,learning) Finish the v2 spec
```

`due` and `tags` are optional. See [`docs/FORMAT.md`](docs/FORMAT.md) for the
full grammar.

## Docs

- [`docs/FORMAT.md`](docs/FORMAT.md) — the `todos.md` line grammar (single source of truth)
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — dev setup & tests

## License

[MIT](LICENSE) © Zhang Yu
