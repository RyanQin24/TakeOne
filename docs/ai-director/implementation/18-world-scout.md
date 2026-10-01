# 18 — World Scout: real locations, a metric planning world, simulated shots

Status: implemented. Live grounding and the photorealistic layer need keys; the
whole flow runs without them on the stored fixture.

## What it does

    IDEA / SCRIPT → LOCATION SCOUT → REAL CANDIDATES → SELECT → PLANNING WORLD
      → STAGE ACTOR + CART → SHOT CANDIDATES → COMPILE ON THE REAL RIG
      → COMPARE ACHIEVED RESULTS → LOCAL REGISTRATION → REHEARSE

The value is not the map. It is that TakeOne builds a metre-space world it is
allowed to reason over, places the actual rig in it, and lets the existing
compiler decide what is possible.

## The licence boundary, in types

Google Photorealistic 3D Tiles are display data. Google Maps Platform terms
forbid machine interpretation, object detection, geodata extraction and derived
offline geometry, so tile content never becomes planning geometry. That is a
type, not a comment:

    WorldEvidence(source="open_map_geometry",           authority=PLANNING,            metric=True)
    WorldEvidence(source="google_photorealistic_tiles", authority=VISUALIZATION_ONLY,  metric=False)

`contracts.WorldEvidence.__post_init__` refuses to build the first shape out of
a tile source. `require_planning_authority` gates every consumer, and
`Obstacle`/`GroundRegion` call it at construction, so a visualization-only
polygon cannot exist. `tests/test_location_scout.py::EvidenceBoundary` pins all
of it, and `apps/rehearsal/tests/location-scout-ui.test.mjs` pins the browser
half — no raycast, no vertex read, no geometry extraction against the tile
layer.

Planning geometry comes from OpenStreetMap over Overpass (ODbL, attributed),
operator measurement, Photo Scout reconstruction, or authored proxies. Only
those four are in `PLANNING_SOURCES`.

## Coordinates: one boundary, then ordinary metres

`GeoAnchor` fixes a local tangent frame at the selected place: `+X` along the
site's compass heading, `+Y` 90° counter-clockwise, `+Z` up, metres.
`geodesy.geodetic_to_local` / `local_to_geodetic` are the only conversion in the
tree. Round-trip error across a 3 km site is under a micrometre
(`GeodeticBoundary.test_round_trips_are_exact_to_a_micrometre_across_the_site`).

Downstream, everything is the metre space TakeOne already used: the planning
world, actor marks, cart marks, `previs.templates` settings, IK, the renderer.
Latitude and longitude never reach the compiler, and ECEF never reaches Three.js
— the tile group carries the inverse ENU matrix as a *display* transform only.

## Modules

    packages/takeone/location_scout/
      contracts.py        WorldEvidence, GeoAnchor, Obstacle, GroundRegion,
                          UnknownRegion, PlanningWorld — the boundary lives here
      geodesy.py          WGS-84 ↔ ENU ↔ site metres. The only conversion.
      parse.py            Maps URL / coordinates / place / search instruction
      grounding_google.py THE Google Maps Platform wire shapes. One file.
      provider.py         Candidate discovery with fixture fallback
      openmap.py          Overpass client and way classification (ODbL)
      planning_world.py   Assembly, including explicit unknown regions
      geometry.py         Small deterministic 2D helpers, no numpy
      affordances.py      Tracking axes, clearance, depth, turning room
      candidates.py       Bounded staging enumeration + cheap world screening
      simulate.py         Compile on the real rig; verdicts and rejections
      digest.py           The scene digest the planner is allowed to see
      planner.py          gpt-5.6-sol at high reasoning, as a planner
      store.py            Regenerable world cache under data/
      api.py              Transport-independent use cases
    apps/rehearsal/dist/
      location.html / location-scout.js / location-scout.css   the scout stage
      location-world.js   tiles + planning overlay, used by the scout and Studio

## HTTP

All loopback-only, bodies capped at 32 kB.

    GET  /api/location-scout/status            providers, model, budgets, tiles
    GET  /api/location-scout/tiles             browser tile config (runtime key)
    GET  /api/location-scout/worlds[/{id}]     cached worlds
    POST /api/location-scout/search            {query, radius_m}
    POST /api/location-scout/select            build the planning world
    POST /api/location-scout/staging           bounded candidates
    POST /api/location-scout/simulate          compile every candidate
    POST /api/location-scout/direct            planner, consent-gated
    POST /api/location-scout/registration      operator local origin

## The AI model

`configs/location-planning.json` selects `gpt-5.6-sol` with
`reasoning: {effort: "high"}` over the OpenAI Responses API. Script planning is
unchanged and still uses `gpt-5.6-luna` — Sol is roughly 17× Luna's output price
and the Director's script budget was sized for Luna.

`director/provider.MODELS` replaces the old hard-coded `luna + max` check with a
reviewed allowlist carrying each model's supported reasoning levels, its
published prices and its output cap. A configuration that names an unknown
model, an unsupported effort, or a price cheaper than the published rate is
refused at construction. Sol's prices, read from developers.openai.com on
2026-09-19: **4.00 USD / 1M input, 20.00 USD / 1M output**, i.e. 4 and 20
microUSD per token, 128k max output.

Budget: 8 000 output tokens and a 24 kB request cap put the reserved worst case
at about 0.18 USD against a 0.30 USD per-request budget. The UI shows the
reserved cost before anything is transmitted.

Sol receives a **digest** — counts, axis lengths, clearances, depths, place
names, the rig's vocabulary and the story. Never polygons.
`test_location_planning.py::RequestShape` walks the payload and fails if any
two-number list survives in it, and walks the response schema and fails if any
leaf is not prose, a rating enum or the bounded `rank` integer. There is no
field in which a coordinate, a joint value or a wheel command could travel.

## Simulation is the authority

Every candidate goes through `previs.templates.compile_template` — the same IK,
joint limits, cart response, scene solve and lens curve Shot Studio uses. Hard
rejections: compiler refusal, joints out of range, a clamped lens, the achieved
cart or actor path inside mapped geometry, or more than half the achieved cart
path over unsurveyed ground. Soft scores are computed only for candidates that
already passed, and `Verdict.total` returns 0 when any failure exists, so a high
score can never rescue a constraint.

Rejected candidates are kept with their reason. So is the cart-pace truth: 4 m
in 6 s needs 0.67 m/s, the policy maximum is 0.50 m/s, so the shot is reported
as running 8.6 s at the command ceiling rather than silently retimed.

## Failure behaviour

| Failure | Result |
| --- | --- |
| No `GOOGLE_MAPS_API_KEY` | stored demo candidates, mode `fixture`, note says why |
| Google Places timeout / 403 / garbage / empty | same fallback, error text kept |
| Overpass unavailable for a real place | planning world with **no** geometry and the whole site marked unknown, plus an explicit offer to use the demo proxy. It never becomes empty floor. |
| No `GOOGLE_MAPS_BROWSER_KEY`, or tile load fails | "Photorealistic context unavailable — planning world still active." Planning world, marks and paths keep rendering. |
| OpenAI unavailable | scouting, world building, staging and simulation all still work; only the cinematic read is missing |
| Unknown world id, traversal attempt | refused by `store.valid_id` |

## Keys

* `GOOGLE_MAPS_API_KEY` — server-side, Places API (New). Never sent to the browser.
* `GOOGLE_MAPS_BROWSER_KEY` — a **separate** key for Map Tiles, served to the page
  at runtime by `/api/location-scout/tiles` and never written into a committed
  file or a log. Restrict it by HTTP referrer to the loopback origin and scope it
  to the Map Tiles API only.
* `OPENAI_API_KEY` — unchanged.

Set them in the shell that starts the simulator. Nothing here reads a `.env`.

## Attribution

Google place data is labelled on every live candidate card. Tile copyright is
aggregated by `GoogleCloudAuthPlugin` and rendered by `location-world.js` into
`#lsAttribution` (scout) and `#worldAttribution` (Studio). It must stay visible
and unobscured whenever tiles render; both are positioned so nothing overlaps
them.

## Demo, in the order it is performed

1. Director → **Scout a location**.
2. Paste `https://www.google.com/maps/@43.466752,-80.5404672,17z`, radius 3 km,
   **Scout locations**.
3. Optionally **Ask the AI Director to read these** — ratings appear as cinematic
   judgement with *physical feasibility: not yet evaluated*.
4. **Preview location** — the planning world builds and the photorealistic layer
   loads behind it.
5. Toggle *Photorealistic context* off: the planning world, marks and path stay.
   That is the whole argument, in one checkbox.
6. **Generate staging**, then **Simulate on the rig**. Passes carry achieved
   numbers; failures carry the reason.
7. **Confirm local registration** with the operator's name.
8. **Rehearse in Shot Studio** → World: *Real location*.

## Known limitations

* Candidate distance is straight-line, labelled as such. No Routes API call is
  made, so no walking time is claimed.
* Overpass is a public service with no SLA. A production demo should pre-warm
  the world for the venue, or bring an operator-measured site.
* Building heights fall back to 6 m when OSM has none; the obstacle records that
  as `open_data_outline_assumed_height`.
* The unknown grid is 6 m. Smaller gaps between mapped features are not resolved.
* The rig's self-clearance check (`previs.scene_checks`) is not run for location
  shots; the metre-world screen replaces it and is nominal, not a safety
  qualification.
* Tile rendering was written against `3d-tiles-renderer` 0.5.3 and verified
  structurally, not against the live Google endpoint, which was unreachable from
  the build environment. The first live run needs a human looking at the screen.
* Nothing here localises the robot. Local registration is an operator claim, and
  real-world cart straightness stays unqualified.
