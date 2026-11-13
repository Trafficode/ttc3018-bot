# PCB machining profiles

Profiles use an app dropdown: **Ścieżki**, **Wiercenie**, **Obrys**.
Printed circuit board (PCB) jobs select operations and enter measured laminate
thickness once. Tool values are stored on the station for phone and desktop.
Drilling and outline profiles do not require V-bit calibration.

## Parameters

| Profile | Basic | Advanced |
| --- | --- | --- |
| Tracks / V-bit | Copper depth, tip, angle, XY feed, calibration | Plunge feed, spindle control |
| Drilling | Diameter, plunge feed, tip overrun into backing, travel clearance | None |
| Outline | Diameter, XY/Z feed, step-down, clearance, separation mode, conditional remaining material and backing entry | None |

Outline tools support 0.5–3 mm diameters; the centreline uses the actual radius.
Round source holes remain separate stages by diameter, 0.3–4 mm. An exact drill
diameter must match every source group. Use “Według pliku PCB” for several sizes.
The engine never silently omits or enlarges holes. Slots remain unsupported.

Preset dropdowns support arrow keys, Enter, Escape and Tab. Existing non-preset
values remain available. A numeric keyboard opens only after **Własna wartość…**.
Only tracks have an advanced section. Spindle percentage represents
the controller's S0–S1000 scale: 30% sends S300. It is not RPM or measured power.
New drilling and simple outline profiles use fixed S1000 (100% control).

Drilling tip depth is exactly laminate thickness plus `drillOverrunMm` (0.05–5 mm).
The operator includes the whole drill point and allowance for uneven material in
this value and provides sufficiently thick backing. There is no automatic cone
addition, declared accuracy budget or assumed backing thickness. Feed and tip
overrun start blank; preset options are choices, not cutting recommendations.
Simple outline profiles use `outlineDepthMode: remaining`. XY/Z feed starts blank.
Skin cuts end at stock thickness minus `remainingMm`. Tabs keep that thickness
only at four bridges; between them the cut enters backing by `millOverrunMm`.
Through cuts use backing entry without retained material. Irrelevant fields are
hidden and excluded from stored values. Stock thickness is still entered per job.

Step-down is a basic editable field, initially 0.2 mm. It is saved explicitly.
There is no Advanced section. Tab width is automatic:
max(3 mm, cutter diameter + 2 mm), displayed beside the separation settings.
New UI saves omit a tab-width override. Old stored overrides remain unchanged
until a reviewed edit is saved; old APIs remain compatible. The server resolves
defaults; engine hashes make results stale when those defaults change.
There are no assumed cutting/backing lengths or separate uncertainty input.
The operator provides adequate cutter length, backing and setup allowances.
Full-through cutting needs a separate job confirmation of secure workholding.

## Storage and compatibility

The version-1 store remains at
`~/.local/share/bark-beetle/pcb-profiles.json`, outside Git, with at most 30
records. Typed records add `kind: drilling|outline`; `activeByKind` holds their
separate selections. Records contain ID, name, revision, fingerprint and tool
values, without laminate thickness. Writes are atomic. Corruption is reported.

Older combined recipes keep their original fingerprints and V-bit binding.
Their original calculation remains available through the legacy API. The new UI
requires an explicit tip overrun before using an old drilling profile. Editing
and saving a typed profile replaces its old drill values with the four simple
values and increments its revision; editing a combined recipe creates a typed
copy and preserves the original. No stored file is silently migrated. The old
combined and isolation-only APIs remain compatible.

Existing outline profiles retain their original values and validation. Editing
them maps skin/tab height to remaining material and breakthrough to backing entry;
only an explicit reviewed save replaces them with the simple profile format.

Saving requires tool review and the previous fingerprint for edits.
Save/select shares the Start lock and is blocked during machining or probing.
Typed mechanical selection never selects a V-bit or contacts the controller.
Legacy selection without a mechanical kind keeps its original V-bit behavior.

## Computer-aided manufacturing (CAM)

Jobs can request all stages, drilling and outline, or any single operation.
Only selected tools are required. Mechanical-only jobs validate the real source
archive and shared coordinates without a V-bit model or isolation sweep claim.
When isolation is selected, its existing sweep check gates the entire result.

Requests freeze selected profile snapshots and per-operation values.
Browser feed overrides are ignored. Profile or engine changes invalidate old
results and require recalculation before stage load or Start.

All routes require `X-PiloMill-Token`; POST requires same-origin JSON.

| Route | Payload / response |
| --- | --- |
| GET `/api/pcb-profiles` | Version, active IDs, records and storage error |
| POST `/api/pcb-profiles/save` | Kind, name, values, confirmedTools; edits add ID and expectedFingerprint |
| POST `/api/pcb-profiles/select` | ID, fingerprint, optional mechanical kind |
| POST `/api/cam/prepare` | Source, operations, processProfiles by kind with ID/fingerprint, material.thicknessMm, confirmations; isolation also supplies profileFingerprint and clearanceMm |

Preparation runs offline with CNC disconnected. Stage load, tool change, fresh Z
preparation and manual Start remain separate operator actions.

## Verification

Tests use temporary stores, real source fixtures and mocked controllers.
They cover legacy data, stale snapshots, independent values, hole grouping,
cutter-radius offsets, full-through confirmation and actual worker output
without V-bit calibration. Desktop/phone checks intercept profile and CAM writes.
No test recipe is saved on the station. Physical cutting remains unverified.
