# new-project

Short description of what this project is and who it is for.

## Status

Scaffold only — no application code yet.

## Workflow

This repo is set up for the addyosmani agent pipeline:

- `/spec <idea>` — write `SPEC.md`; references become the core idea
- `/plan` — break the spec into `tasks/plan.md`
- `/auto` — run spec → plan → build → test → review → ship, one model per step
- `/commit`, `/push` — git operations on the cheapest model

Each completed task gets its own commit and push.

## Structure

| Path | Purpose |
| --- | --- |
| `SPEC.md` | requirements and locked intent (created by `/spec`) |
| `tasks/plan.md` | ordered, verifiable tasks (created by `/plan`) |
| `docs/references/` | notes and snapshots for external references |

## Development

Commands will be added once the stack is chosen in `SPEC.md`.
