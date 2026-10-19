# ---------------------------------------------------------------------------
# feed.py
# 2026-10-19
# - Per-job horizontal feed selection without changing plunges or uploads.
# ---------------------------------------------------------------------------
"""Prepare a validated execution copy before surface compensation."""

import math

from monitor.jobs import WORD, parse_program


def with_xy_feed(program, value):
    """Override level XY G1 moves; retain original ramp and Z-only feeds."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or (
        not math.isfinite(value) or not 1 <= value <= 300
    ):
        raise ValueError("Posuw XY musi wynosić 1–300 mm/min.")
    position = {axis: None for axis in "XYZ"}
    motion = None
    original_feed = None
    commands = []
    for line in program["lines"]:
        words = WORD.findall(line["code"])
        values = {letter: float(number) for letter, number in words
                  if letter in "XYZF"}
        for letter, number in words:
            if letter == "G" and float(number) in (0, 1):
                motion = int(float(number))
            elif letter == "G" and float(number) == 80:
                motion = None
        if "F" in values:
            original_feed = values["F"]
        axes = {axis: values[axis] for axis in "XYZ" if axis in values}
        if axes and motion not in (0, 1):
            raise ValueError("Po G80 wymagany jawny ruch G0 lub G1.")
        target = {**position, **axes}
        command = line["code"]
        if axes and motion == 1:
            horizontal = any(
                axis in axes and position[axis] is not None
                and abs(target[axis] - position[axis]) > 1e-9
                for axis in "XY"
            )
            level = target["Z"] == position["Z"]
            selected = value if horizontal and level else original_feed
            # Explicitly restore original modal feed on every other G1 move.
            command = "".join(letter + number for letter, number in words
                              if letter != "F") + f"F{selected:g}"
        commands.append(command)
        position = target
    result = parse_program(program["name"], "\n".join(commands))
    for line, original in zip(result["lines"], program["lines"]):
        line["source_line"] = original["source_line"]
    result["xy_feed"] = value
    return result

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
