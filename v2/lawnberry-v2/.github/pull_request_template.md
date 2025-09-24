# LawnBerry Pi v2 Pull Request

## Description
<!-- Describe the change in 1–3 sentences. Link to related task/issue if applicable. -->

---

## Checklist

- [ ] **Agent Journal Updated**
  - Updated `memory/AGENT_JOURNAL.md` with:
    - Current task status
    - Decisions made
    - Next debug steps
    - Handoff notes

- [ ] **Docs Updated**
  - Updated `/docs` and `/spec` to reflect this change
  - If no docs needed, explain why:

- [ ] **Tests**
  - [ ] Unit tests added/updated
  - [ ] Integration tests (sim mode or hardware-in-the-loop where applicable)
  - [ ] All tests passing locally (`uv run pytest`)

- [ ] **CI**
  - [ ] Lint checks pass (`ruff`, `black`, `mypy`)
  - [ ] No unapproved TODOs (`TODO(v3)` only with issue link)
  - [ ] No doc drift (CI docs job passes)

---

## Notes for Reviewers
<!-- Any special notes, instructions, or caveats for reviewers. -->
