# Bandra Dispatch — Project Instructions

Vehicle routing & dispatch simulator: FastAPI + NetworkX + SciPy backend
(`/backend`), React + Vite + Tailwind frontend (`/frontend`). Real OSMnx street
network for Bandra, Mumbai; 50 vans across 5 depots.

## Required reading

**Before making any change to the simulation logic** (backend `app/*.py`, or any
frontend code that assumes a particular backend behavior), read
`SIMULATION_LOGIC.md` at the project root. It documents every constraint, cost
formula, algorithm choice, and known edge case in the system — the tick/movement
physics, the depot balancing algorithm, the logistics capacity constraint, the
per-depot Hungarian dispatch, the vehicle lifecycle, the cost model, and
operational gotchas that have already been debugged once (don't rediscover them).

## Standing rule: keep `SIMULATION_LOGIC.md` in sync

**Whenever a feature is added or changed in this simulation, update
`SIMULATION_LOGIC.md` in the same pass — after the feature has been tested, not
before.** This applies to both backend logic changes and frontend changes that
encode a rule (e.g., new marker states, new tab, new metric). Treat an
out-of-date `SIMULATION_LOGIC.md` as an incomplete feature, the same way you'd
treat a failing test or a missing verification step.

What "update" means concretely:
- New constant, threshold, or formula → document it with its value and why.
- New endpoint or WebSocket payload field → add it to the API section.
- New algorithm or changed assignment logic → describe the approach and any
  measured before/after result (this repo's history shows real numbers matter —
  e.g. the depot node split went from `[426, 20, 133, 120, 387]` to `[250, 250,
  196, 183, 207]` after a fix, and that's the kind of concrete evidence worth
  keeping).
- New bug found and fixed → add it to "Operational gotchas" so it isn't
  silently reintroduced or re-debugged from scratch later.

Do not skip this because the change feels small. Small undocumented drift is
exactly how this kind of reference doc rots.

## Verification expectations

This project has working dev servers (backend on :8000, frontend on :5174 —
port 5173 is often occupied by an unrelated project on this machine, do not
kill it without checking what it is). When adding or changing simulation
behavior:
- Prefer testing against the live running servers over static code review.
- For anything touching dispatch, movement, or the depot constraint, a stress
  test via `POST /api/orders/bulk` is the fastest way to surface edge cases —
  several real bugs in this codebase were only found under load (e.g. a
  one-way-street pathfinding crash that only triggered once per few hundred
  return trips).
- The simulation's background tick loop is fire-and-forget
  (`asyncio.create_task`, never awaited) — an unhandled exception inside it
  fails **silently**: the API keeps responding to HTTP requests normally, but
  `tick` in `/api/metrics` stops advancing. Always confirm `tick` is still
  climbing across two spaced-out checks after a change, not just that the last
  request returned 200.
