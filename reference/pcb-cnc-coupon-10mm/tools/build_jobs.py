# ---------------------------------------------------------------------------
# build_jobs.py
# 2026-10-12
# - Adapt the reviewed pcb2gcode coupon export and check emitted motions.
# ---------------------------------------------------------------------------
"""Create offline spindle-off and cutting files; never access CNC hardware."""

import argparse
import hashlib
import importlib.util
import json
import math
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WORD = re.compile(r"([A-Z])([+-]?(?:\d+(?:\.\d*)?|\.\d+))")


def read_cam():
    """Accept this one-tool linear export, rejecting unexpected operations."""
    raw_path = ROOT / "cam/raw/isolation-raw.ngc"
    content = raw_path.read_text(encoding="ascii")
    if "( pcb2gcode 3.0.4 )" not in content:
        raise ValueError("Review required for a different CAM version")
    commands = []
    for line in content.splitlines():
        line = re.sub(r"\([^()]*\)", "", line).strip()
        if line:
            commands.append("".join(line.split()).upper())
    allowed = {"G": {0, 1, 4, 21, 90, 94}, "M": {0, 2, 3, 5, 9}}
    for command in commands:
        words = WORD.findall(command)
        if "".join(letter + value for letter, value in words) != command:
            raise ValueError("Unexpected CAM syntax: " + command)
        for letter, value in words:
            number = float(value)
            if not math.isfinite(number) or letter not in "GMXYZFSPT":
                raise ValueError("Unexpected CAM word: " + command)
            if letter in allowed and number not in allowed[letter]:
                raise ValueError("Unsupported CAM operation: " + command)
            if letter == "T" and command != "T1":
                raise ValueError("More than one tool in CAM export")
            if letter == "S" and number != 1000:
                raise ValueError("Unexpected spindle setting")
            if letter == "F" and number not in (30, 100):
                raise ValueError("Unexpected feed")
            if letter == "Z" and number not in (-0.05, 3):
                raise ValueError("Unexpected depth or retract")
    expected_header = [
        "G94", "G21", "G90", "G00S1000", "G01F100.00000",
        "G00Z3.00000", "T1", "M5", "G04P0.00000", "M0", "M3",
        "G04P2.00000", "G04P0", "G00Z3.00000",
    ]
    expected_footer = ["M5", "G04P0.000000", "M9", "M2"]
    if commands[:14] != expected_header:
        raise ValueError("CAM startup changed: review before adaptation")
    if commands[-4:] != expected_footer:
        raise ValueError("CAM shutdown changed: review before adaptation")
    body = commands[14:-4]
    if any(letter in "MST" for line in body
           for letter, value in WORD.findall(line)):
        raise ValueError("Control operation inside toolpath")
    if not body or not body[0].startswith("G00X"):
        raise ValueError("Missing initial XY toolpath move")
    return body


def make_job(body, air):
    """Prepend a centreline square, then retain the CAM isolation moves."""
    description = "AIR CHECK - spindle off" if air else "CUT - enables spindle"
    lines = [f"; {description}; provisional V30 tip0.1 coupon recipe",
             "; Work zero: copper surface, lower-left corner of 10mm square",
             "; Confirm 3mm Z clearance over all crossed stock and clamps",
             "G21 G90 G94 G54", "M5", "G0 Z3"]
    if not air:
        lines.extend(("M3 S1000", "G4 P2"))
    # The visual square is centreline marking, not compensated cut-through.
    border_z = 1 if air else -0.07
    lines.extend(("G0 X0 Y0", f"G1 Z{border_z:g} F30",
                  "G1 X10 Y0 F100", "G1 X10 Y10", "G1 X0 Y10",
                  "G1 X0 Y0", "G0 Z3"))
    for command in body:
        if air:
            # Preserve XY paths and feeds. Lift only cutting Z to 1mm.
            command = re.sub(r"Z-0\.05000(?=[A-Z]|$)", "Z1", command)
        lines.append(command)
    lines.extend(("G0 Z3", "M5", "M30"))
    return "\n".join(lines) + "\n"


def movements(program, air):
    """Check rapid clearance and record every segment for plotting."""
    point = {"X": None, "Y": None, "Z": None}
    motion = None
    segments = []
    for line in program["lines"]:
        words = [(letter, float(value))
                 for letter, value in WORD.findall(line["code"])]
        for letter, value in words:
            if letter == "G" and value in (0, 1):
                motion = int(value)
        axes = {letter: value for letter, value in words if letter in "XYZ"}
        if not axes:
            continue
        old = point.copy()
        point.update(axes)
        if "X" in axes or "Y" in axes:
            if motion == 0 and point["Z"] != 3:
                raise ValueError("XY rapid without 3mm clearance")
            if old["X"] is not None and old["Y"] is not None:
                segments.append({"from": [old["X"], old["Y"]],
                                 "to": [point["X"], point["Y"]],
                                 "z": point["Z"], "motion": motion})
        if air and point["Z"] < 1:
            raise ValueError("Air file descends below 1mm work Z")
        if not air and point["Z"] < -0.07:
            raise ValueError("File descends beyond shallow marking depth")
    return segments


def main():
    """Use the actual panel validator and save source-linked evidence."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--validator", required=True, type=Path,
                        help="Path to the deployed monitor/jobs.py source")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("job_validator",
                                                args.validator)
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    body = read_cam()
    output = ROOT / "cam/jobs"
    output.mkdir(exist_ok=True)
    report = {"cam": "pcb2gcode 3.0.4 a5604c4, no GEOS",
              "physical_acceptance": "UNVERIFIED", "files": {},
              "effective_isolation_diameter_mm":
              0.1 + 2 * 0.05 * math.tan(math.radians(15)),
              "sha256": {}}
    for air, name in ((True, "01-air-check.nc"),
                      (False, "02-copper-mark-and-isolate.nc")):
        content = make_job(body, air)
        program = validator.parse_program(name, content)
        segments = movements(program, air)
        expected_z = [1.0, 3.0] if air else [-0.07, 3.0]
        assert program["bounds_mm"] == {
            "X": [0.0, 10.0], "Y": [0.0, 10.0], "Z": expected_z,
        }
        path = output / name
        path.write_text(content, encoding="ascii")
        report["files"][name] = {
            "validation": "PASS", "commands": len(program["lines"]),
            "bounds_mm": program["bounds_mm"],
            "max_feed_mm_min": program["max_feed"],
            "max_controller_s": program["max_power"],
            "segments": segments,
        }
        report["sha256"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
    sources = [ROOT / "cam/raw/isolation-raw.ngc", ROOT / "cam/millproject",
               ROOT / "manufacturing/cnc-coupon-10mm-F_Cu.gtl",
               ROOT / "cnc-coupon-10mm.kicad_pcb", args.validator]
    for path in sources:
        report["sha256"][path.name] = hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
    destination = ROOT / "validation/cam.json"
    destination.write_text(json.dumps(report, indent=2) + "\n",
                           encoding="utf-8")
    for name, item in report["files"].items():
        print(name, "PASS", item["commands"], item["bounds_mm"])


if __name__ == "__main__":
    main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
