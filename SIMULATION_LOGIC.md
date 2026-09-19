# Simulation Logic Reference

This document is the single source of truth for every rule, constraint, and design
decision in the Bandra Dispatch simulator's backend. It exists so the *why* behind
the code doesn't have to be re-derived from scratch every time someone (human or
Claude) touches this repo. See the update rule at the bottom.

---

## Where we left off (2026-07-13, end of session)

- **Live state:** backend (`:8000`) and frontend (`:5174`) both running, simulation
  reset to a clean idle baseline — 100/100 vans idle, 0 orders, tick counter still
  climbing normally. Servers were left running; nothing needs restarting to pick
  this back up, just confirm `curl localhost:8000/api/metrics` still responds and
  `tick` is advancing before assuming the session is healthy.
- **Everything in this doc is current as of this session** — fleet is 100 vans / 7
  depots, SLA target is 18 minutes, depot placement uses the Lloyd's-refinement
  algorithm in §4.
- **Open item for next session:** §10's stress-test capacity numbers (backlog
  behavior, SLA decay curve, drain time) are still from the *old* 50-van/10-min
  config. They have not been re-measured at the current 100-van/7-depot/18-min
  scale. If picking dispatch/capacity work back up, run a fresh `+300` (or
  larger) stress test first and update §10 with real numbers before relying on
  the old ones — the fleet roughly doubled and the SLA window grew 80%, so the
  old figures are likely stale in the *optimistic* direction (new setup should
  handle more load), but that's a prediction, not something to build on
  unverified.
- No other in-progress work at close of that session — the last verified state
  was a clean 100-order smoke test showing balanced dispatch across all 7 depots
  with no errors. **Update 2026-09-19:** re-verifying §4's numbers turned up two
  unfixed bugs (5 nodes unreachable from every depot → orders there are never
  dispatched; depot assignment one re-centering round stale). See §11, "Open
  issues" — a 100-order smoke test has only about a 37% chance of landing even
  one order on the unreachable nodes (1 − (1 − 5/1086)^100), and a single stuck
  order is easy to miss among 100.

---

## 1. What this is

A vehicle routing & dispatch simulator for a delivery fleet operating in Bandra,
Mumbai: currently **100 vans across 7 depots** (`app/state.py:TOTAL_VEHICLES`,
`app/graph_setup.py:NUM_DEPOTS` — these are the two numbers to change if the
fleet is resized again; everything else derives from them), serving delivery
orders on the real OSMnx-derived drivable street network, with live traffic, a
depot capacity constraint, and a cost-accounting model. Backend: FastAPI +
NetworkX + SciPy. Frontend: React + Vite + Tailwind + react-leaflet.

Fleet/depot history: launched at 50 vans / 5 depots; scaled to 100 vans / 7
depots. Vans are split across depots as evenly as possible
(`state.vans_per_depot`) — with 100/7 this is 14 or 15 per depot, not a flat
constant, so per-depot costs and capacities can differ slightly between depots.

---

## 2. Time & movement physics

- **1 backend tick = 1 real second = 1 real second of simulated driving time.**
  No time compression. `tick_count` is literally elapsed seconds since the last
  reset. (`app/simulation.py:TICK_SECONDS = 1.0`)
- Vehicles move **continuously along real road geometry**, not node-by-node. Each
  van tracks `route_path` (node list), `route_cum_dist` (cumulative meters at each
  node), `route_progress_m`, and `route_total_m`. Every tick, progress advances by
  `effective_speed_mps * 1.0`, and lat/lon are linearly interpolated between the
  two path nodes the current progress falls between.
- Speed comes from real OSM data: `speed_kph` per edge (from `osmnx.add_edge_speeds`),
  converted to m/s, divided by that edge's live congestion multiplier.
- `MIN_EFFECTIVE_SPEED_MPS = 1.4` (~5 km/h) — a floor so gridlock slows a van but
  never fully freezes it.

## 3. Traffic simulation (`app/traffic.py`)

- Every edge gets a stable `base_intensity` (0.25–1.0, seeded from the edge's own
  id so it's reproducible) and a random `phase`.
- Each tick: `congestion = 1 + base_intensity * (MAX_MULTIPLIER - 1) * wave`, where
  `wave = 0.5 + 0.5*sin(tick/45 + phase)` and `MAX_MULTIPLIER = 2.6`. This produces
  a slow oscillating "rush hour wave" per edge, not a single global number.
- `current_weight = travel_time * congestion` — this is the edge weight used for
  **both** the Hungarian dispatch cost matrix (route/van selection) **and** for
  live vehicle speed (`effective_speed = base_speed / congestion`). Depot-node
  partitioning (§4) deliberately does **not** use this live value — see why below.
- The map's traffic overlay shows the top 40 most-congested segments only (not all
  ~2,474 edges) — a performance/legibility tradeoff, not a correctness one.

## 4. Depot placement & the balanced partition

Depot placement is a **Lloyd's-iteration refinement loop** (`app/state.py::
_init_depots`), not a single pass — this was needed because the seeding step and
the balancing step each solve a different problem, and neither alone was enough:

1. **Seed** `NUM_DEPOTS` candidate locations by farthest-point sampling using
   **real road-network travel time** (Dijkstra), not straight-line lat/lon
   (`app/graph_setup.py::pick_depot_nodes`). Straight-line distance was tried
   first and produced badly uneven depots (one "owned" 39% of the network by
   nearest-node count, another 1.8%) because geometric spread ≠ network
   reachability on a real street layout (one-ways, dead ends, coastline).
2. **Balance** (`_balanced_assignment`) — plain nearest-depot argmin is still
   not enough even with good seeding: a **regret-based greedy capacitated
   assignment** runs each round:
   - Every node is ranked: which depot is nearest, which is 2nd-nearest (by
     free-flow `travel_time`, congestion-independent — this partition must stay
     stable regardless of live traffic).
   - "Regret" = (2nd-nearest distance − nearest distance). Nodes are processed
     in descending regret order, so nodes with a strong single preference claim
     their depot first; flexible nodes (small regret) get pushed to their 2nd
     (or 3rd...) choice if the nearest one is already at its target capacity.
   - Target capacity per depot = `ceil(node_count / NUM_DEPOTS * BALANCE_SLACK)`,
     `BALANCE_SLACK = 1.15`.
3. **Re-center** — after each balancing pass, every depot's location is moved to
   the node nearest the lat/lon centroid of *its own assigned partition*, then
   step 2 re-runs against the new locations. `DEPOT_REFINEMENT_ROUNDS = 4`.
   This step exists because farthest-point seeding alone can strand one depot in
   a network-sparse corner — "maximally far from the others" is not the same as
   "near a lot of streets." Re-centering pulls a stranded depot toward wherever
   its (even if currently tiny) partition actually is, and it grows from there.

**Measured results** (real runs of the `state.py` code paths, not estimates):

- **5-depot era — historical, not the current layout.** Those arrays have 5
  elements because the fleet had 5 depots then: node split **[250, 250, 196,
  183, 207]**, vs. **[426, 20, 133, 120, 387]** with plain nearest-depot argmin
  on the same 5 depot points (fixed by step 2 alone, before the fleet was
  scaled to 7 depots). It is not re-measurable on the current code without
  reverting `NUM_DEPOTS`; the 7-depot equivalent is the table below.
- **Current 7-depot layout, 1,086 nodes, re-measured 2026-09-19.** Balance cap
  = `ceil(1086 / 7 * 1.15)` = 179 nodes per depot. Avg/max are free-flow
  depot→node travel time in seconds, computed against the depot positions each
  variant actually uses. "Unreachable" = nodes with no directed path from their
  assigned depot; they are excluded from avg/max (they'd be `inf`).

  | Variant | Node split per depot | Unreachable | Avg | Max |
  |---|---|---|---|---|
  | (a) plain nearest-depot, seed points | [279, 271, 176, 98, 188, 13, 61] | 0 | 136.1 s | 271.1 s |
  | (b) balanced only, seed points (no step 3) | [179, 179, 179, 179, 179, 13, 178] | 0 | 189.8 s | 640.4 s |
  | (c) balanced + 4 re-centering rounds — **production** | [97, 179, 170, 135, 179, 172, 154] | 5 | 82.5 s | 325.0 s |
  | (d) plain nearest-depot at the final depot points | [94, 199, 147, 119, 220, 178, 129] | 5 | 77.2 s | 325.0 s |

  - (b) is the "before re-centering" result: one depot stranded at 13/1086
    nodes, reproducing the original imbalance problem one depot at a time.
  - (c) vs (b): re-centering removes the stranded depot and cuts **average
    travel time to the assigned depot from 189.8 s to 82.5 s** (2.3x), max from
    640.4 s to 325.0 s. This is the concrete "optimize delivery time" result
    from re-centering.
  - (d) shows what the balancing constraint costs: without it two depots blow
    past the 179-node cap (199 and 220) in exchange for ~5 s less average
    travel time (77.2 s vs 82.5 s).
  - **Correction to the previously recorded figure.** This section used to say
    "189.8 s → 87.5 s, max 640 s → 305 s". That was avg/max over the reachable
    nodes only, measured against the depot positions from *before* the final
    re-centering (see §11, "Open issues"), so it did not match the depots as
    they are actually placed. Against the final positions it is 82.5 s / 325.0 s.
    The 7-element splits in (b) and (c) were reproduced exactly.

`nearest_depot_index(node)` is a static lookup into the final precomputed
assignment, not a live computation — cheap and stable per node for the life of
the sim. Re-running placement (adding/removing depots) requires a backend
restart, not just a `/api/reset` — depot count and locations are fixed at
`SimulationState.__init__`.

## 5. Order lifecycle & the depot logistics constraint

States: `pending → assigned → completed`, or `pending → waitlisted → pending → …`.

- **`DEPOT_BATCH_CAPACITY = 60`** — the max orders a depot may have *active*
  (`pending` + `assigned`, i.e. not yet completed) at once. This is a concurrency
  cap, not a lifetime cap — completing orders frees capacity immediately.
- New order arrives → assigned a home depot (§4) → `state._route_new_order`:
  - If that depot is currently **restocking** → waitlisted, no new restock timer.
  - Else if `active_order_count >= 60` → **this** order gets waitlisted, and the
    depot enters restock: `restock_until_tick = tick + RESTOCK_TICKS (600 = 10
    min)`, `waitlist_events += 1`.
  - Else → accepted as `pending`, `orders_handled_total += 1`.
- Every tick, `SimulationState.drain_waitlists()` releases FIFO from any
  non-restocking depot's waitlist back into `pending` as capacity frees up — this
  runs continuously, not just the instant a restock timer expires, so a depot
  under 60 active orders keeps absorbing its backlog even mid-restock-cooldown of
  a *different* depot.
- Depot Analytics exposes, per depot: `orders_handled_total`, `active_orders`,
  `waitlist_length`, `waitlist_events`, `is_restocking`, `restock_remaining_sec`.

## 6. Dispatch algorithm (the optimization model)

**Per-depot Hungarian assignment**, not one global assignment:

- For each depot: gather its **idle** vans (all share `current_node ==
  depot.node`, because vans return home between deliveries — see §7) and its
  **pending** orders (already home-depot-filtered by §4/§5).
- **One** `nx.single_source_dijkstra` per depot (not per vehicle!) from the depot
  node, `weight="current_weight"` (live, congestion-aware) → distances/paths to
  every order in that depot's queue.
- Cost matrix (idle × pending) fed to `scipy.optimize.linear_sum_assignment`.
  Unreachable pairs get a `1e9` sentinel and are dropped from the final match.
- This is a **capacitated multi-depot VRP, decomposed** into (a) a balanced
  nearest-depot partition (§4) that also enforces the logistics constraint (§5),
  and (b) per-partition optimal (Hungarian) assignment. Efficiency win:
  `NUM_DEPOTS` Dijkstra calls/tick instead of up to `TOTAL_VEHICLES` (one per
  idle van, the pre-partition design) — 7 vs. up to 100 at current scale.

## 7. Vehicle lifecycle

`idle → en_route → (delivery complete) → returning → (arrival) → idle`

- Only **idle** vans are dispatch-eligible. A `returning` van cannot be
  redirected mid-trip — it must reach its home depot first (this was an explicit
  requirement, not just an implementation shortcut).
- `lifetime_distance_m` accumulates **both** the delivery leg and the empty
  return leg — this feeds the depot's fuel cost total (§8), so "cost of running
  this depot" honestly includes deadheading, not just loaded trips.
- **Known edge case, fixed:** one-way streets can make the *directed* path from a
  delivery's drop-off node back to the depot node not exist, even though the
  *outbound* depot→order path existed (asymmetric reachability in a directed
  graph). `nx.shortest_path` raises `NetworkXNoPath` in that case.
  - Fix: try the directed graph first; on `NetworkXNoPath`, fall back to
    `state.undirected_graph` (`graph.to_undirected(as_view=True)`, precomputed
    once — a view, not a copy). This is guaranteed to succeed, since outbound
    directed reachability implies undirected reachability along the same edges.
  - This bug **silently killed the entire simulation loop** in production before
    the fix — see §11 "Operational gotchas."

## 8. Cost model

**Fixed costs** — one-time, charged once per simulation (not accumulated over
time), computed as a constant from depot/van counts:

| Line item | Amount | Allocation |
|---|---|---|
| Warehouse operation cost | ₹1,000 | per depot |
| Utility | ₹100 | per depot |
| Van driver salary | ₹500 | per van |
| Fleet maintenance | ₹60 | per van |

Per depot: `1000 + 100 + van_count*(500+60)`. Van count is per-depot (see §1 —
100 vans / 7 depots splits as 14 or 15 per depot), so this is no longer a flat
number across depots: currently **₹9,500** for a 15-van depot, **₹8,940** for a
14-van depot. Total fixed at current scale (7 depots, 100 vans): **₹63,700**.
(At the original 50 vans / 5 depots: ₹6,700/depot flat, ₹33,500 total.)

> **Assumption flagged to the user, not explicit in the original spec:**
> warehouse ops & utility are warehouse-level (per depot); driver salary &
> maintenance are vehicle-level (per van) — the natural real-world split for each
> line item. If this assumption is ever revisited, update `state.py`'s
> `WAREHOUSE_OPERATION_COST` / `UTILITY_COST` / `VAN_DRIVER_SALARY` /
> `FLEET_MAINTENANCE_COST` constants and this section together.

**Variable costs** — accrue continuously:

| Line item | Amount | Trigger |
|---|---|---|
| Fuel charge | ₹100/km | every km actually driven, **including empty return-to-depot legs** |
| Warehouse refill cost | ₹500 | every time a depot enters restock mode (one charge per `waitlist_events` increment) |

- **Per-delivery** records (Delivery Log tab) show only the **outbound** leg's
  distance/fuel cost — "what this delivery cost," not deadheading.
- **Depot/global** totals (Depot Analytics tab, `metrics.total_cost_of_operation`)
  include both legs — "what it costs to run this depot," honestly.
- `total_cost_of_operation = total_fixed_cost + total_variable_cost`, live and
  growing over the run.

## 9. SLA & backlog/ETA analytics

- `SLA_THRESHOLD_SEC = 1080` (18 minutes — raised from the original 10-minute
  target). A delivery is "on time" if `completed_tick - created_tick <= 1080`.
- The metrics field is `sla_pct` (renamed from `sla_10min_pct` when the
  threshold changed, so the name doesn't silently lie about the window size —
  same rename applied to the internal `state.sla_within_threshold` counter).
  Frontend labels read the actual window from `metrics.sla_threshold_sec`
  rather than hardcoding "10 min"/"18 min" text — if the threshold changes
  again, update `SLA_THRESHOLD_SEC` in `state.py` only; the UI follows
  automatically (`Sidebar.jsx`, `MapView.jsx`'s SLA-breach marker coloring).
- `sla_pct` defaults to **100%** when there are zero completed deliveries yet
  (avoids a misleading 0%/undefined reading on a fresh sim).
- **This is a measured outcome, not a guaranteed constraint.** Verified finding:
  injecting orders faster than the fleet's sustainable service rate (see §10)
  produces a real backlog, and SLA genuinely drops below 100% as backlogged
  orders' wait time accumulates before their van even starts driving. Do not
  present the SLA threshold as an enforced guarantee in UI copy — it's a target
  the system is measured against, and it will visibly fail under enough load.
- **ETA/backlog** (`BacklogStatus` on the frontend):
  `backlog_remaining = (all orders not yet completed) + (orders still queued to
  be created)`. Throughput is estimated from the last `COMPLETION_WINDOW = 30`
  completions' timestamps; if the newest of those is more than
  `STALE_RATE_TICKS = 60` ticks old, the rate is treated as unreliable and
  `eta_sec` is `null` ("estimating…") rather than extrapolating from stale data.
- **Other metrics fields worth knowing about:** `total_vehicles`, `total_depots`
  (both derived counts, so the UI never hardcodes fleet size — see the
  Sidebar footer and SLA badge label, which read these plus
  `sla_threshold_sec` instead of static text).

## 10. Stress testing — sequential injection

- `POST /api/orders/bulk {count}` **enqueues** `count` into
  `bulk_queue_remaining` — it does **not** create orders immediately.
- The tick loop creates **exactly one** new random order per tick while
  `bulk_queue_remaining > 0` — literal one-per-second sequential injection, not a
  burst. This was an explicit requirement change from an earlier "create all N
  instantly" design.
- Frontend buttons: **+100 / +200 / +300** (`MAX_BULK_ORDERS = 300` server-side cap).
- **Verified capacity finding (at 50 vans / 5 depots, 10-min SLA — pre-scaling
  baseline):** each delivery took ~3–6 minutes real time in this compact
  network, sustaining roughly 12–13 deliveries/minute. A +300 batch injected
  over 5 minutes demands a peak rate several times that — a genuine queueing
  overload, not a bug. Backlog built to a peak of ~175–297 pending across two
  separate runs; SLA dropped from 100% into the 67–86% range depending on how
  long the run was allowed to continue (it degrades further the longer an
  overloaded batch runs, since backlogged orders keep accruing wait time). A
  +300 batch takes on the order of **25–30 minutes** to fully drain. This is the
  system being honestly measured under load, not a defect to "fix" by hiding
  the backlog.
- **Not yet re-verified at 100 vans / 7 depots / 18-min SLA.** The fleet
  roughly doubled and the SLA window grew 80%, both of which should raise
  sustainable throughput and the backlog the system can absorb before SLA
  erodes — but this is a prediction, not a measurement. Before quoting a
  capacity number at the new scale, rerun a +300 (or larger) stress test and
  update this section with the actual result, the same way the 50-van baseline
  above was captured.

## 11. Operational gotchas (don't rediscover these)

- **Fire-and-forget asyncio task swallows exceptions.** `SimulationEngine._run()`
  is started via `asyncio.create_task` and never awaited/checked. An unhandled
  exception inside `tick()` kills the loop **permanently and silently** — the
  FastAPI server keeps responding to HTTP requests normally (so `curl
  /api/metrics` looks fine except `tick` never advances), which makes this
  extremely easy to miss. `_run()` now wraps `self.tick()` in try/except and
  `logging.exception(...)`s any failure before continuing to the next tick. If
  you ever see `tick` stop advancing while the server still responds, check the
  uvicorn log for `"Simulation tick failed"` first.
- osmnx's `nearest_nodes` on an unprojected graph requires `scikit-learn` as an
  optional dependency — already in `requirements.txt`, but if you rebuild the
  venv from scratch and hit `ImportError: scikit-learn must be installed...`,
  that's why.
- Port `5173` is frequently occupied on this machine by an unrelated project
  (`GlobalOSInt-Demo`). The frontend is configured for port **5174** with
  `strictPort: true`; backend CORS allows both 5173 and 5174. Don't "fix" port
  conflicts by killing whatever's on 5173 without checking what it is first.
- The GraphML cache at `backend/data/bandra_mumbai.graphml` round-trips edge
  attributes as strings — `graph_setup.load_graph()` re-casts `travel_time`,
  `length`, and `speed_kph` to float on every load. If you add a new numeric edge
  attribute anywhere, remember to cast it here too or it'll silently behave as a
  string (e.g., string concatenation instead of addition) after a cache reload.
- **Adding depots can silently strand one of them with almost no orders.**
  Going from 5 to 7 depots reproduced the original load-imbalance bug on a
  smaller scale: one new depot landed with only 13/1086 nodes even *after* the
  regret-based balancing in §4, because the seed location itself was in a
  network-sparse spot — balancing a partition can't fix a bad seed, only
  redistribute around it. Fixed by adding the re-centering/Lloyd's-iteration
  step (§4, step 3). If you ever change `NUM_DEPOTS` again, re-run the balanced
  node-count check (see §4's measured results) before trusting the new
  placement — don't assume the seeding+balancing pipeline degrades gracefully
  without checking.
- `Depot.fixed_cost()` and vehicle counts are **per-depot** (`Depot.van_count`),
  not a shared flat constant — `TOTAL_VEHICLES / NUM_DEPOTS` rarely divides
  evenly. `state.vans_per_depot()` distributes the remainder to the first few
  depots. Don't reintroduce a flat `VEHICLES_PER_DEPOT`-style constant; it will
  silently misallocate vans (and therefore fixed cost) the next time the totals
  don't divide evenly.
- **CARTO's free anonymous basemap tiles are dead — the map used to render
  via `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png`
  (`frontend/src/components/MapView.jsx`), which required no key. CARTO has
  since locked this down: every tile request against that host (and its
  `cartodb-basemaps-*.global.ssl.fastly.net` alias, and the `/rastertiles/`
  path variant) now returns HTTP 200 with a watermarked "API KEY REQUIRED"
  placeholder image instead of map data — confirmed with a plain `curl`, so
  it's not a browser/CORS issue. There is no free-tier key fix without
  signing up for a CARTO account. Replaced with Esri's keyless
  `World_Dark_Gray_Base` tile service
  (`https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`
  — note the `{z}/{y}/{x}` order, not `{z}/{x}/{y}`), with `maxNativeZoom={16}`
  since Esri's source tiles don't go past zoom 16 (Leaflet upsamples beyond
  that). If the map ever shows "API KEY REQUIRED" again, it's this same CARTO
  deprecation, not a regression in this repo — swap providers again rather
  than debugging the app code.

### Open issues (found 2026-09-19 while re-verifying §4's numbers; **not fixed**)

Both were found by running the real code, not by reading it, and neither is
fixed yet. Fix them together and re-measure §4's table afterwards — changing
the assignment can change which nodes end up unreachable.

1. **5 of 1,086 nodes are unreachable from every depot, so orders placed there
   are never dispatched.** The street graph is *not* strongly connected
   (`nx.is_strongly_connected(graph)` is `False`; one-way streets leave
   directed sinks). The seed layout reached all 1,086 nodes, but after
   re-centering (§4 step 3) no depot has a directed path to these 5: OSM node
   ids `245664547`, `245668275`, `346604267`, `1936355432`, `10082236370`.
   Dispatch gives unreachable pairs the `1e9` sentinel and drops them (§6), so
   such an order just sits in `pending`. **Confirmed live:** an order dropped at
   `245664547` (19.05068, 72.83700) was still `pending` after 32 s while a
   control order created at the same moment was `assigned` within 8 s, with
   plenty of idle vans. Exposure: random mock/bulk orders pick uniformly from
   all graph nodes (`random.choice(list(state.graph.nodes))`), so ~0.46% of them
   (5/1086) hit this; interactive drop-mode clicks near those spots can too.
   A stuck order inflates `backlog_remaining`, never completes, and drags
   `sla_pct` down for the rest of the run. Candidate fixes (unverified): restrict
   the graph to its largest strongly connected component in `load_graph()`, or
   only generate/accept orders on nodes reachable from their home depot.
2. **The stored depot assignment is one Lloyd round stale.** `_init_depots`
   re-centers the depots (M-step) *after* the last balanced assignment (E-step)
   and never re-runs the E-step, so `_node_depot_assignment` — what
   `nearest_depot_index` routes orders by — describes the depot positions from
   *before* the final move, not where the depots actually sit. Recomputing the
   balanced assignment at the final depot positions changes the home depot of
   **134 of 1,086 nodes**. (§4 step 3's "then step 2 re-runs against the new
   locations" is therefore true for rounds 1–3 but not after the last round.)
   `_depot_free_flow_dist` is affected the same way and is written once
   (`state.py:185`) but not read anywhere else in `app/`, so it's currently a
   dead attribute. Candidate fix: one more E-step after the loop.

---

## Update rule

**Whenever a feature is added or changed in this simulation, and after it has
been tested, this document must be updated in the same pass** — new constraints,
changed constants, new endpoints/fields, new known edge cases, all belong here.
Treat an out-of-date `SIMULATION_LOGIC.md` as an incomplete feature, the same way
you'd treat a failing test. This rule itself is enforced via `CLAUDE.md` at the
project root so it survives across sessions.
