# Agent instructions

For coding agents working in this repository: Claude Code, Codex, Cursor, Gemini, Kimi, Pi and the rest. People start with `README.md`; the DS_Business_Process build starts with `ds_business_process/README.md`.

## Shared memory

- At session start, read the shared memory: `scripts/memory.sh brief`. Before work on a topic an earlier session may have touched, run `scripts/memory.sh recall <words>`.
- Before you finish, save the decisions, corrections and findings a later session needs and cannot find by reading the repository. Read `.agents/skills/project-memory/SKILL.md` before your first save.
- Memory supplements the record. Decisions are on the record only in `ds_business_process/registers/decision-register.md` (DSBP-DEC-0048 set up this memory).

## Checks

Run `scripts/check.sh` before you push. It runs every test, the memory tests among them.
