# Revision A validation — 2026-10-12

## Scope and result

PASS for native geometry and the configured design rules. Physical CNC
capability is UNVERIFIED. This is a passive, board-only machining coupon;
electrical rules check, schematic parity and circuit simulation are not applicable.

Authoritative files: `../cnc-coupon-40mm.kicad_pcb` and
`../cnc-coupon-40mm.kicad_pro`. Hashes are recorded in `geometry.json`.

## Tools and provenance

- KiCad CLI and native Python/pcbnew: **10.0.6**.
- Installed editing and validation skills: printer-study-toolkit electronics
  engineering **0.3.0**; direct API fallback used because no KiCad MCP tool was
  exposed in this chat. No second server or tool installation was performed.
- Consuming project's toolkit checkout: `b49f118ec6dc9237206e67b1a3710410133cecdf`;
  the pre-existing worktree is dirty and was not edited for this project.
- Native standard footprints from the installed KiCad 10 library; custom
  diagnostic footprints are included in `../CncCoupon.pretty`.
- SVG/PDF rendered directly by KiCad CLI; PNG rasterized from that SVG with
  PyMuPDF. The preview includes F.Cu, F.Silkscreen and Edge.Cuts, without mirroring.

## Checks

| ID | Requirement and evidence | Result |
| --- | --- | --- |
| G01 | Four connected outline segments; 40 × 40 mm endpoint extent | PASS |
| G02 | Reloaded eight trace widths: 1.0 down to 0.2 mm | PASS |
| G03 | Reloaded sixteen independent H/V edge gaps: 1.0 down to 0.2 mm | PASS |
| G04 | Eight drill diameters and annular rings measured from native pads | PASS |
| G05 | Four fiducial centres form a 36 × 36 mm square | PASS |
| G06 | XY0 marker equals auxiliary origin, 5 × 5 mm from top-left | PASS |
| D01 | DRC errors, warnings and exclusions; zero reported violations | PASS |
| D02 | Native connectivity; zero unconnected items | PASS |
| V01 | Rendered top-view labels, pads, holes and copper bars inspected | PASS |
| E01 | ERC, schematic parity, simulation; no schematic/circuit | N/A |
| B01 | Actual milling, repeatability, soldering and clamping | UNVERIFIED |

The 0.001 mm comparison tolerance in geometry verification is a digital-model
check, not a claim of machine accuracy. Dimensions are product requirements
or explicitly selected experimental geometry, not validated manufacturing limits.

## Rules and exclusions

Experimental DRC minima: 0.2 mm track width/clearance, 0.6 mm drill diameter,
1.5 mm copper-to-edge clearance and 0.6 mm silkscreen text height.
There are no per-item DRC exclusions. KiCad's template leaves five categories
ignored: missing courtyard, track-to-via centring, tuning geometry, footprint
filter mismatch and footprint type mismatch. These are listed in `drc.json`.
All diagnostic footprints have courtyards; there are no vias, tuning profiles,
schematic footprint filters or functional netlist to validate.

The standard 0.4–0.5 mm CNC production recommendation is not replaced by these
coupon-specific rules. Fields below 0.4 mm are intentionally exploratory.

## Repair history and final evidence

Initial DRC found small annotation heights and one courtyard overlap near
SOIC-8 and F3. Explicit text-height rules were set for the reference map and
SOIC-8 was moved right. No copper-clearance or connectivity failure was waived.
The final DRC returned zero violations and zero unconnected items. Final SVG,
PDF and PNG were regenerated from the same saved board and visually inspected.

## Reproduction

Run with installed KiCad Python: `tools/build_coupon.py`, then
`tools/verify_coupon.py`. Rebuild before rerunning the CLI commands below.
Paths are relative to the coupon directory; use your installed `kicad-cli`.

```text
kicad-cli pcb drc --format json --severity-all --all-track-errors --exit-code-violations --output validation/drc.json cnc-coupon-40mm.kicad_pcb
kicad-cli pcb export svg --layers F.Cu,F.Silkscreen,Edge.Cuts --page-size-mode 2 --mode-single --black-and-white --output validation/layout.svg cnc-coupon-40mm.kicad_pcb
kicad-cli pcb export pdf --layers F.Cu,F.Silkscreen,Edge.Cuts --mode-single --black-and-white --output validation/layout.pdf cnc-coupon-40mm.kicad_pcb
```

These commands do not create machine G-code, open USB or operate hardware.
