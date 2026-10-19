# ---------------------------------------------------------------------------
# compensation.py
# 2026-10-19
# - Bilinear PCB height compensation of validated absolute linear programs.
# ---------------------------------------------------------------------------
"""Build a separate validated execution stream; never mutate an upload."""

import math

from monitor.jobs import WORD, parse_program


def height_at(surface, x, y):
    """Interpolate inside the complete rectangle; never extrapolate."""
    area = surface.area
    if not area["X"][0] - 0.0001 <= x <= area["X"][1] + 0.0001 or not (
        area["Y"][0] - 0.0001 <= y <= area["Y"][1] + 0.0001
    ):
        raise ValueError("Ruch poza zmierzoną mapą; kompensacja zablokowana.")
    u = (x - area["X"][0]) / (area["X"][1] - area["X"][0])
    v = (y - area["Y"][0]) / (area["Y"][1] - area["Y"][0])
    u = min(max(u, 0), 1) * (surface.columns - 1)
    v = min(max(v, 0), 1) * (surface.rows - 1)
    column = min(int(u), surface.columns - 2)
    row = min(int(v), surface.rows - 2)
    a, b = u - column, v - row
    # Samples arrive in serpentine order; index explicitly by grid cell.
    def cell(r, c):
        index = c if r % 2 == 0 else surface.columns - 1 - c
        return surface.samples[r * surface.columns + index]["z"]
    return ((1 - a) * (1 - b) * cell(row, column)
            + a * (1 - b) * cell(row, column + 1)
            + (1 - a) * b * cell(row + 1, column)
            + a * b * cell(row + 1, column + 1))


def live_offset(replies):
    """Read G54 + G92 + tool offset from a fresh GRBL $# response."""
    coordinates = {}
    tool = None
    for line in replies:
        if line.startswith("[TLO:") and line.endswith("]"):
            tool = float(line[5:-1])
        for name in ("G54", "G92"):
            if line.startswith(f"[{name}:") and line.endswith("]"):
                coordinates[name] = [float(v) for v in line[5:-1].split(",")]
    if tool is None or set(coordinates) != {"G54", "G92"} or any(
        len(values) != 3 for values in coordinates.values()
    ):
        raise ValueError("Nie można potwierdzić aktualnego zera mapy.")
    result = [coordinates["G54"][i] + coordinates["G92"][i]
              + (tool if i == 2 else 0) for i in range(3)]
    if not all(math.isfinite(v) for v in result):
        raise ValueError("Niepoprawne zero mapy.")
    return result


def compensate_program(program, surface):
    """Split feed moves to <=0.5 mm XY and retain global rapid clearance."""
    if not surface.valid or len(surface.samples) != len(surface.points):
        raise ValueError("Brak kompletnej, aktualnej mapy powierzchni.")
    lines = []
    sources = []
    position = {"X": None, "Y": None, "Z": None}
    motion = None
    raised = max(0, max(sample["z"] for sample in surface.samples))
    spacing = min(
        0.5,
        (surface.area["X"][1] - surface.area["X"][0]) / (
            surface.columns - 1
        ) / 2,
        (surface.area["Y"][1] - surface.area["Y"][0]) / (
            surface.rows - 1
        ) / 2,
    )

    def append(code, source):
        lines.append(code)
        sources.append(source)
        if len(lines) > 20000:
            raise ValueError("Kompensacja przekracza limit 20000 poleceń.")

    for original in program["lines"]:
        words = WORD.findall(original["code"])
        axes = {letter: float(value) for letter, value in words
                if letter in "XYZ"}
        for letter, value in words:
            if letter == "G" and float(value) in (0, 1):
                motion = int(float(value))
            if letter == "G" and float(value) == 80:
                motion = None
        if not axes:
            append(original["code"], original["source_line"])
            continue
        target = {**position, **axes}
        prefix = "".join(letter + value for letter, value in words
                         if letter not in "XYZ" and not (
                             letter == "G" and float(value) in (0, 1)
                         ))
        if motion == 0:
            if target["Z"] is None or target["Z"] <= 0:
                raise ValueError("G0 pod powierzchnią: brak kompensacji.")
            output = {**axes, "Z": target["Z"] + raised}
            code = prefix + "G0" + "".join(
                f"{axis}{value:.4f}" for axis, value in output.items()
            )
            append(code, original["source_line"])
        elif motion == 1:
            if any(value is None for value in position.values()):
                raise ValueError("Brak pozycji przed ruchem kompensowanym.")
            length = math.hypot(target["X"] - position["X"],
                                target["Y"] - position["Y"])
            count = max(1, math.ceil(length / spacing))
            if len(lines) + count > 20000:
                raise ValueError("Za dużo odcinków kompensacji.")
            for step in range(1, count + 1):
                point = {axis: position[axis] + (target[axis] - position[axis])
                         * step / count for axis in "XYZ"}
                point["Z"] += height_at(surface, point["X"], point["Y"])
                code = (prefix if step == 1 else "") + "G1" + "".join(
                    f"{axis}{value:.4f}" for axis, value in point.items()
                )
                append(code, original["source_line"])
        else:
            raise ValueError("Nieobsługiwany ruch kompensacji.")
        position = target
    result = parse_program(program["name"], "\n".join(lines))
    result["compensated"] = True
    result["xy_feed"] = program.get("xy_feed")
    for line in result["lines"]:
        line["source_line"] = sources[line["source_line"] - 1]
    return result

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
