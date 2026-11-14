# Service panel design check

Final result: PASS for local implementation against the existing panel's
compact technical visual language. Physical CNC use and RPi deployment were
not part of this check.

Source: existing Bark Beetle Zero view and its shared styles, rendered with
simulated HTTP state. Implementation: new Service view with the same header,
navigation, controls, camera placement and operator confirmation dialog.
This is a feature extension; source and implementation content differ.

Comparison evidence is kept locally under `.local/service-qa/` in the authoring
workspace. `source-1440.png` / `source-390.png` and `ready-1440.png` /
`ready-390.png` were combined for side-by-side inspection. Captures are not
stored in Git, as required by AGENTS.md.

Findings corrected:

- Main controls fell below secondary inputs on phones: collapsed fixed session
  settings, reduced map height, retained the depth control as the primary input.
- Range input margins caused two pixels of horizontal overflow: removed them.
- Map annotations were too small: increased their font size and moved the
  centre height below the point, away from the strip contour.

Final checks: no horizontal overflow at 1440 x 900, 390 x 844 or 360 x 740;
visible active/disabled control states; five progress points and measured Z
values; clip-removal gate; separate scan/cut confirmation; no command on slider
edits; exactly one explicitly confirmed cut; completed-trial profile saving.
Small-height screens retain vertical scrolling for secondary history.

The tool/geometry extension was checked at the same three viewports: visible
Frez V and Próbka modules, editable strip width after mapping, live theoretical
groove output, changed-tool map guard, and no horizontal overflow. Tip and angle
edits are passive. The readout distinguishes a theoretical width from a measured
result. Speed controls remain in their own module below the sample settings.

Depth-offset regression check: the actual SVG contour spacing minus its rendered
stroke width remains the selected strip width when depth doubles. The backend
G-code is checked separately across 30 tool/depth/width combinations. SVG uses
native hyphenated stroke/anchor attributes so the browser renders the computed
groove width rather than a default one-pixel stroke.

Manual movement extension: custom decimal/comma step entry is passive; invalid
values disable movement and Z is disabled above its per-command limit. The
top-bar correction status is visible. Service trial history contains submitted
parameters and generated geometry for comparison; default has no correction.

## Measured profile extension — 2026-10-24

Final result: PASS for software and responsive UI. Physical accuracy remains
unverified until the operator measures milled samples.

The existing technical panel is the visual source. Added a compact profile
selector and explicit formula in the same top status area; a collapsed profile
module in Serwis contains observation selection, actual strip measurements,
creation, export and deletion. Existing milling controls retain their layout.

Local evidence is under `.local/profile-qa/`, outside Git. Source and rendered
captures at matched viewport sizes were compared together. First mobile review
found notification text squeezed into a narrow column beside the selector.
The corrected status area wraps the selector onto its own row. Revised captures
show readable status text, visible coefficients and no horizontal overflow.

Playwright passed 1440 x 900, 390 x 844 and 360 x 740: no action on editing,
creation requires two observations and does not select the profile; selection
updates the formula and predicted groove; tool/speed fields lock to measured
conditions; out-of-range depth disables probing; JSON export contains both
observations and a fingerprint; selection survives reload; active deletion is
disabled. No browser test connects to real CNC endpoints.

Python tests include fitted and nominal geometry, calibrated scan/cut evidence,
atomic persistence, damaged-store blocking, stale profile rejection, motion
interlocks, matching CAM metadata, and the PC helper preserving original NC
commands. Existing probing and job tests remain passing.

Manual entry follow-up: the primary form accepts tool conditions and 2–8 typed
measurement rows without history IDs. Each row shows depth, nominal strip,
actual strip and explicit CAM diameter. Creation remains enabled before data
entry and produces actionable validation on click. History-based creation is
an optional collapsed section. Browser checks passed at all three viewport
sizes: empty-name/missing-value errors, no automatic commands, exact manually
entered values, profile selection, predicted service diameter and JSON export.
Evidence: local `.local/profile-qa/manual-*.png`. Physical cutting was not run.

Single-observation follow-up: one manual row is now sufficient and is the
default. The resulting model keeps the nominal angle slope and offsets its
diameter, with correction and measurement depth visible in the top bar. Other
depths are explicitly described as predictions; no artificial zero RMS is shown.
Browser QA passed all three sizes, including invalid-measurement feedback beside
the form, successful save feedback, a stale poll overlapping save, immediate
selector refresh, applying the profile to service geometry, export and reload.
Evidence: `.local/profile-qa/single-*.png`. Tests do not create live RPi profiles.

## Dedicated profile test — 2026-10-24

Final result: PASS for the software workflow; physical cutting remains
unverified. Profiles now occupy their own tab. Creation and revision controls
are collapsed, while the selected fixed conditions, test plan and explicit
probe/cut actions form the primary flow. Service fields remain editable under
any selected profile and use only nominal tool geometry.

The SVG and generated G-code share backend paths: 10 mm copper strips of
0.3/0.5/1 mm and opposite-vertex octagon diameters 1/2 mm. Nine signed Z samples
appear on the same preview. Real footprint dimensions include tool clearance.
Mobile tabs use compact icons above labels to fit all six tabs without page
overflow. Tab changes reset the content scroll position.

Browser QA at 1440 x 900, 390 x 844 and 360 x 740 passed fixed-depth profile
creation, independent service settings, five preview contours, nine probe
markers and measured values, no auto-cut, clip gate, separate confirmations,
one explicit test cut and immutable revision creation. Captures remain local
under `.local/profile-qa/test-plan-*.png` and `test-map-*.png`. Existing visual
language was compared against the earlier service/profile captures; the added
profile test and mobile navigation are intentional scope changes.

## Simplified settings and probe diagnostics — 2026-10-24

Final result: PASS for the software workflow. One selector loads the profile,
with horizontal Settings/Test views and an explicit test CTA. Settings have
direct save/delete/new actions, preset dropdowns with a custom fallback, and
descriptions of cutting depth, tool tip/angle, XY feed, vertical entry feed
and spindle S. History-based creation and nested profile panels are removed.

Browser checks at the three standard sizes passed default jog F300, blocked
probe before contact, required release while contact is closed, enabled zero
after release, 10 mm confirmation, profile creation, editing without another
list entry, test access and confirmed deletion of the selected profile. There
were no unexpected machine commands or horizontal page overflow. Captures are
local `simple-settings-*`, `simple-test-*` and `simple-zero-*` under
`.local/profile-qa/`. Backend tests cover 10 mm limits, manual-contact latching,
atomic editing, snapshots, stale CAM rejection and return to Default on delete.

## Tight test bounds and neutral browser tabs

The test now bounds actual tool sweep and adds exactly 1 mm per side, without
the old 10 mm minimum height. Backend assertions cover all four margins and
unchanged copper dimensions. The preview canvas follows the shorter rectangle.
Settings/Test tabs use one shared neutral browser-tab style, a content-colored
active tab connected to its panel, and identical active/hover rules. The Test
tab no longer has a permanent primary-action class. Keyboard arrows and
Home/End move focus and selection. Browser checks compare computed active
styles in both views at all three standard sizes, plus the existing complete
profile/probe/cut/delete flow. Final result: PASS; captures remain outside Git.

## Manual finishing pass

The Test view explains the local 0.5 mm rapid approach, retains the completed
height map and shows a separate finishing card only after successful completion.
The card contains completed pass count, cleaning guidance, one unchanged-setup
checkbox and a deliberate repeat button. A separate modal confirms one pass
without additional depth. Invalid snapshots display the reason instead of a
start button. Completion messages distinguish a fresh test from a finishing pass.

Browser checks at all three sizes passed: no auto-repeat, checkbox and modal
gates, one manual finishing request, no additional probe request, pass count
increment and cleared confirmation after completion. Local evidence:
`.local/profile-qa/finish-*.png`. Backend tests verify local approach heights,
full XY clearance, byte-identical replay without double compensation, no new
calibration observation, live-offset checks and invalidation on disconnect
or profile selection. Final result: PASS for software; physical cuts unverified.
