# `todos.md` Format

The single source of truth for the on-disk format. The server's `data.py` and
any compatible tool (e.g. a CLI editing the same file) must agree on this grammar.

## File layout

```
# Todos

<!-- Format: - [ ] #ID [priority] (due: YYYY-MM-DD) (tags: a,b) text -->

- [ ] #1 [high] (due: 2026-06-01) (tags: agent,learning) Finish the v2 spec
- [x] #2 [med] Read the MCP spec
- [ ] #3 [low] (tags: chore) Clean up logs
```

The first four lines (title, blank, format comment, blank) are regenerated on
every write — don't rely on hand-edits there surviving.

## Line grammar

```
- [STATUS] #ID [PRIORITY] (due: YYYY-MM-DD)? (tags: tag1,tag2)? TEXT
```

| Field    | Values                                   | Required |
|----------|------------------------------------------|----------|
| STATUS   | ` ` (open) or `x` (done)                 | yes      |
| ID       | positive integer, unique                 | yes      |
| PRIORITY | `high` / `med` / `low`                   | yes      |
| due      | `YYYY-MM-DD`                             | optional |
| tags     | comma-separated, each `[a-z0-9_-]+`      | optional |
| TEXT     | free text, single line                   | yes      |

The optional segments are order-fixed: **due before tags**, both before TEXT.

## Tags

- Lowercase; allowed characters `[a-z0-9_-]`.
- No spaces, commas, or parentheses inside a tag (the comma is the separator;
  parentheses would break the segment).
- On input, tags are lowercased, trimmed, de-duplicated (order preserved);
  invalid characters raise an error.
- Serialized as `(tags: a,b,c)`; an empty tag list omits the segment entirely.

## Invariants

- **IDs are monotonically increasing and never reused.** Removing a todo
  retires its ID forever, keeping cross-references stable.
- Lines that don't match the grammar are **silently ignored on read** and
  **dropped on write** — don't store free-form notes in the file.

## Backward compatibility

The `(tags: ...)` segment is optional and was added in v0.2.0. Files written
by v0.1.x (no tags) parse unchanged. Any other tool sharing the file must
adopt this same grammar, or it will misparse the `(tags: ...)` segment into the
text field and corrupt it on the next write.
