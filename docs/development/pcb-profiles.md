# PCB machining profiles

A job selects one saved setup and supplies measured laminate thickness. Tool
parameters are configured once in Profiles. The complete recipe is stored on the
station, so desktop and phone use the same values. This is separate from the
measured V-bit width/depth calibration; each recipe pins that calibration too.

## What belongs where

| Scope | Values | Reason |
| --- | --- | --- |
| Every board | Profile choice, measured laminate thickness, mounting confirmation | Thickness changes cut depth; probing Z does not measure thickness. |
| Saved profile: tools | Drill feed and S; end-mill XY feed, plunge, S, step-down and cutting length | These describe the actual cutter/material setup. Never infer them from V-bit settings. |
| Saved profile: mounting | Backing thickness, travel clearance | Reuse while the physical mounting remains unchanged. Update when backing or clamps change. |
| Advanced profile | Drill point angle, breakthrough allowance, thickness/Z uncertainty, skin and tab dimensions | Required geometry or declared margins, rarely changed per board. Information buttons explain each. |
| Optional job override | Skin thickness or four-tab retention | Reuses the recipe while allowing the requested method of separation. |
| Calculated | Drill diameters/groups from source, tip correction, final depths, pass count | Do not ask the operator to enter derived values. |

The engine supports a 1 mm outline end mill; its diameter is not an editable job
field. Initial skin 0.20 mm, uncertainty 0.05 mm, clearance 3 mm, breakthrough
0.20 mm and tabs 3 by 0.30 mm are existing editable setup values, not validated
universal cutting settings. The initial 118-degree drill point must match the
actual drills. Feeds, S, cutting length and backing thickness remain blank in a
new profile until supplied. S is controller scale, not measured spindle RPM.

Material and mounting expands with a visible chevron. It shows saved backing,
clearance and uncertainty, plus the job's optional separation override. A new
material, cutter or mounting needs a suitable profile; hiding a field does not
remove its server validation or physical verification requirement.
The skin/tab selector uses the application's own popover in both job and profile
views, including selected-state marking, arrow keys, Enter, Escape and Tab.

## Storage and revision rules

The version-1 JSON store is `~/.local/share/bark-beetle/pcb-profiles.json`.
It contains an active ID and at most 30 recipes. Each recipe has an ID, name,
revision, fingerprint, V-bit calibration reference and validated values. Measured
laminate thickness is deliberately excluded. Writes are atomic; malformed stored
data is reported and never silently replaced. This operator data is not in Git.

Saving requires explicit tool/mounting review. Editing uses the previous
fingerprint to reject stale browser data. Selection verifies and selects the
pinned V-bit calibration using the existing controller owner; it does not open
USB, probe or start a program. Saving and selection share the Start lock and are
blocked during an active job or probe.

CAM requests freeze the full profile snapshot. The server accepts only measured
thickness and optional skin/retention from the material override. It resolves
feeds, S and clearance from the saved profile. A changed recipe requires a new
calculation and blocks stage load and Start, rather than changing old NC files.

## API

All routes require the existing `X-PiloMill-Token`. POST also requires same-origin
JSON, at most 8192 bytes. The package-ingestion bearer token grants no access.

| Route | Payload / response |
| --- | --- |
| GET `/api/pcb-profiles` | Version, active ID, profiles and storage error. |
| POST `/api/pcb-profiles/save` | Name, values, `confirmedTools: true`; updates add ID and `expectedFingerprint`. Returns the saved recipe. |
| POST `/api/pcb-profiles/select` | ID and fingerprint. Returns selected recipe after checking its V-bit binding. |
| POST `/api/cam/prepare` | Source identity, `profileFingerprint`, `processProfileId`, `processFingerprint`, material, `confirmedDatum` and `confirmedSetup`. Returns the immutable CAM attempt. |

Legacy explicit-workflow CAM requests remain compatible. New UI requests use the
saved-profile path. No endpoint starts machining as a side effect of profile use.

## Compact navigation and verification

Main tools are Move, Zero, File and Profiles. Manual spindle controls are an
expandable section in Move. Camera and Service use labelled icon buttons in the
topbar. Camera is closed initially and allocates space only when opened. The map
preview remains available inside File even while camera is closed.

Browser checks cover desktop 1440 by 1024 and phone 390 by 844, empty-profile
onboarding, profile editing, one visible numeric job field, disclosure arrows,
information popovers and Escape, optional skin override and the resulting CAM
payload. Profile writes and CAM preparation are intercepted in browser tests;
no test recipe is inserted into the production station store. Backend tests use
temporary stores and mocked serial ports. Physical milling remains unverified.
