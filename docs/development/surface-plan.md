# PCB surface measurement plan

The File tab includes the selected inline surface-plan layout. It derives a
rectangular sample grid from the uploaded program's X/Y bounds in G54 work
coordinates. Positive X points right and positive Y points up. The diagram
preserves the aspect ratio; it shows machining bounds, not the physical PCB edge.

Choose 3 x 3, 5 x 5 or a custom grid of 2 to 11 points per axis. The default
includes the complete boundary. Points are numbered in alternating row order;
the list provides their exact X/Y coordinates. Area editing can extend the
bounds, but cannot omit a programmed region. The plan does not infer clamps,
stock shape or available copper from G-code.

Settings remain selected while switching operator tabs. Loading or clearing a
file resets them. Plans are browser-local, session-only preparation and do not
represent measured heights, machine calibration or saved compensation maps.
Changing plan settings sends no CNC command. Active jobs lock plan editing.
The execution buttons remain outside the scrolling file contents.

## Current scope

This File section implements the planning UI only. The Start measurement button
is disabled with an explicit explanation. Probe diagnostics and single-point
automatic Z zero are available separately in [Zero](z-probe.md). Grid height
acquisition and surface Z compensation are not implemented.
Existing milling executes the original validated program without compensation.
No generated illustration of traces is presented as an actual file preview.

Further grid measurement work must use the existing serial owner and preserve
the single-point probing guards. It must also add coordinate/map invalidation
and compensation coverage checks. The operator initiates all motion.

## Validation

Run `npm ci` and `npm run build` from `ui/`. From the repository root run
`node tests/test_surface_plan.cjs` and `node tests/test_web.cjs`.
Local browser checks use a simulated API. They cover grid presets, custom
dimensions, invalid inputs, coverage validation, exact point lists, tab changes,
file changes, disabled probing and portrait layouts at 390 and 360 px.
