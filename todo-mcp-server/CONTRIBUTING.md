# Contributing

Thanks for your interest! This is a small, focused MCP server — bug fixes,
tests, and well-scoped features are all welcome.

## Dev setup

Requires Python >= 3.10.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Run the checks

```bash
pytest          # tests
ruff check .    # lint
```

Both must pass before a PR is merged; CI runs them on Python 3.10–3.13.

## Conventions

- **`data.py` stays MCP-agnostic** — it only reads/writes `todos.md`. Protocol
  wiring belongs in `server.py`; the browser layer in `dashboard.py`. Keep the
  three separated.
- **The on-disk format is a contract.** Any change to the line grammar must
  update [`docs/FORMAT.md`](docs/FORMAT.md) and keep old files parseable.
- Add tests for new behavior — `tests/` mirrors the modules.
- Keep tools' type hints and docstrings accurate: the MCP SDK turns them into
  the schema/description the LLM actually sees.

## Manual smoke test

```bash
todo-mcp-server --project-root /tmp/demo
# then open the dashboard URL printed to stderr
```
