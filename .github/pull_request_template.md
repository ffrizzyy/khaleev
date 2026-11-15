## What changed and why

<!-- One paragraph: the behaviour before, the behaviour after, and the reason. -->

## SPEC

<!-- The locked-intent item this implements (e.g. "locked intent 18"), or "none: docs and repo housekeeping". -->

## Gates

- [ ] Backend, from `backend/`: `uv run ruff check .` and `uv run pytest -q`
- [ ] Frontend, from `frontend/`: `npm run lint`, `npm run build`, `npm test -- --run` and `npx prettier --check .`
- [ ] Class scan, from the repository root: `node tasks/class-scan.mjs frontend/src` prints `(none)` for both lists and exits 0
- [ ] No pre-existing test file was edited, or the edited files and the reason are named above
- [ ] Visual change: checked in a browser at 360px and 1280px wide (tick without checking if the change is not visual)

## Notes for the reviewer

<!-- Known gaps, follow-ups, or anything you would challenge in this diff. -->
