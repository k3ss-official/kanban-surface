# Work-ledger format

Kanban Surface reads a deliberately small Markdown contract. This keeps Git useful to humans while giving the synchroniser stable identifiers.

## Core rule

Every card imported from Git has a unique `cm_ref`. Do not recycle identifiers after completion; stable references make reconciliation and receipts idempotent.

## MASTER.md

Use five columns in this order:

```markdown
| ID | Item | Owner | Status | Notes |
|---|---|---|---|---|
| M1 | Prove the deployment path | engineering-lead | active | Test against a disposable target |
```

Accepted identifiers match `M` followed by digits. The generated reference is the identifier itself, for example `M1`.

## Daily files

Store daily notes as `daily/YYYY-MM-DD.md` and use:

```markdown
| ID | Item | Ties | Owner | Status |
|---|---|---|---|---|
| D1 | Verify the release receipt | M1 | audit-controller | awaiting |
```

Accepted identifiers match `D` followed by digits. The generated reference combines date and row ID, for example `2026-08-14#D1`. A non-empty Ties value becomes the card note `ties: <value>`.

## Project next actions

Project files can expose ordered actions under a `## Next` heading:

```markdown
# Example project

## Next

1. Complete the permission-gateway threat model
2. Run the negative-token acceptance test
```

Generated references include the path and list position, for example `projects/example.md#next-1`. Project next actions enter as `backlog`. Struck-through items are ignored.

## Cardable statuses

These normalised statuses enter the board:

- `active`
- `backlog`
- `needs-decision`
- `blocked`
- `awaiting`

`done`, `later`, and superseded work remain in Git. The parser also recognises these status markers:

- `✅` → `done`
- `⏳` → `awaiting`
- `◐` → `active`

Any status beginning with `blocked` normalises to `blocked`.

## Generated card body

The synchroniser writes linkage data at the top of each card:

```text
cm_ref: M1
source: MASTER.md
owner: engineering-lead
notes: Test against a disposable target
```

`cm_ref` is the machine linkage key. Do not remove or edit it manually.

## Safe authoring rules

- Keep IDs unique and stable.
- Use one table row per work object.
- Do not place literal `|` characters inside cells.
- Keep project actions as ordered list items directly under `## Next`.
- Use synthetic examples in this repository; keep customer and operational data in your private ledger.

## Verification

Run the parser and integration suites:

```bash
python3 tests/test_cm_parser.py
python3 tests/test_integration.py
```
