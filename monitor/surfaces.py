# ---------------------------------------------------------------------------
# surfaces.py
# 2026-10-18
# - File-bound grid measurements using the existing guarded probe runner.
# ---------------------------------------------------------------------------
"""Reference touch, safe Z travel, serpentine sampling and map validity."""

import math
import secrets
import time

from monitor.probes import ZProbe


def plan_grid(bounds, payload):
    """Build coordinates on the RPi; never trust a client point list."""
    counts = []
    for name in ("columns", "rows"):
        value = payload.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or (
            not 2 <= value <= 11
        ):
            raise ValueError("Siatka: 2–11 punktów na każdej osi.")
        counts.append(value)
    columns, rows = counts
    area = payload.get("area")
    if not isinstance(area, dict):
        raise ValueError("Brak obszaru pomiaru.")
    result = {}
    for axis, limit in (("X", 300), ("Y", 180)):
        values = area.get(axis)
        if not isinstance(values, list) or len(values) != 2 or not all(
            isinstance(v, (int, float)) and not isinstance(v, bool)
            and math.isfinite(v) for v in values
        ):
            raise ValueError("Niepoprawne granice pomiaru.")
        low, high = values
        original = bounds[axis]
        if not -limit <= low < high <= limit or (
            original[0] is None or original[1] is None
            or low > original[0] or high < original[1]
        ):
            raise ValueError("Siatka musi obejmować cały zakres pliku.")
        result[axis] = values[:]
        count = columns if axis == "X" else rows
        if (high - low) / (count - 1) < 0.01:
            raise ValueError(
                "Rozstaw sondowania musi wynosić co najmniej 0,01 mm."
            )
    points = []
    for row in range(rows):
        for column in range(columns):
            index = columns - 1 - column if row % 2 else column
            points.append({
                "number": len(points) + 1,
                "x": result["X"][0] + index * (
                    result["X"][1] - result["X"][0]
                ) / (columns - 1),
                "y": result["Y"][0] + row * (
                    result["Y"][1] - result["Y"][0]
                ) / (rows - 1),
            })
    return result, points


class SurfaceScan(ZProbe):
    """One probe lease covers the reference touch and all XY/Z operations."""

    def __init__(self):
        super().__init__()
        self.map_id = None
        self.job_id = None
        self.valid = False
        self.reason = None
        self.points = []
        self.samples = []
        self.area = None
        self.offset = None
        self.reference = None
        self.reference_xy = None
        self.sampling = False
        self.clearance = 2

    def active(self):
        return super().active() or self.state in ("xy_ack", "xy_wait")

    def invalidate(self, reason):
        """Keep diagnostic results but never reuse them as compensation."""
        if self.map_id is not None:
            self.valid = False
            self.reason = reason

    def status(self):
        result = super().status()
        result.update({
            "kind": "surface", "id": self.map_id, "job_id": self.job_id,
            "valid": self.valid, "reason": self.reason, "area": self.area,
            "points": self.points, "samples": self.samples,
            "reference_xy": self.reference_xy,
            "completed": len(self.samples), "total": len(self.points),
            "columns": getattr(self, "columns", None),
            "rows": getattr(self, "rows", None),
        })
        return result

    def start(self, controller, payload):
        program = controller.jobs.program
        if program is None or payload.get("job_id") != controller.jobs.job_id:
            raise ValueError("Plik zmienił się; odśwież plan.")
        area, points = plan_grid(program["bounds_mm"], payload)
        clearance = float(payload.get("clearance", 2))
        below = float(payload.get("below", 1))
        if not math.isfinite(clearance) or not 1 <= clearance <= 3 or (
            not math.isfinite(below) or not 0.1 <= below <= 2
            or clearance + below > 5
        ):
            raise ValueError("Prześwit 1–3 mm, zakres pod zerem 0,1–2 mm.")
        if controller.offset is None:
            raise ValueError("Brak odczytu WCO; zaczekaj na status CNC.")
        result = super().start(controller, payload)
        self.reference_xy = controller.report["position"][:2]
        self.expected_xy_offset = controller.offset[:2]
        self.map_id = secrets.token_hex(12)
        self.job_id = controller.jobs.job_id
        self.columns = payload["columns"]
        self.rows = payload["rows"]
        self.area, self.points = area, points
        self.samples = []
        self.valid = False
        self.reason = None
        self.offset = None
        self.reference = None
        self.sampling = False
        self.clearance, self.below = clearance, below
        self.feed = float(payload["feed"])
        return result

    def _write(self, controller, command, state):
        if command == "G0Z1":
            command = f"G0Z{self.clearance:g}"
        super()._write(controller, command, state)

    def _check_offset(self, controller):
        if self.offset is not None and controller.offset is not None:
            if any(abs(a - b) > 0.002 for a, b in zip(
                self.offset, controller.offset
            )):
                raise RuntimeError("Zero zmieniło się podczas pomiaru.")

    def _next(self, controller):
        if len(self.samples) == len(self.points):
            self.state = "completed"
            self.valid = True
            self.lease = None
            return
        point = self.points[len(self.samples)]
        position = controller.report["position"]
        length = math.hypot(point["x"] - position[0],
                            point["y"] - position[1])
        self.deadline = time.monotonic() + length / 100 * 60 + 10
        self._write(controller,
                    f"G1X{point['x']:.4f}Y{point['y']:.4f}F100", "xy_ack")

    def _accept(self, controller, line):
        if line == "ok" and self.state == "xy_ack":
            self.state = "xy_wait"
            self.query_at = 0
            return
        special = self.state in ("xy_ack", "xy_wait", "retract_wait") or (
            self.sampling and self.state == "contact_wait"
        )
        if not line.startswith("<") or not special:
            super()._accept(controller, line)
            return
        controller._accept_status(line)
        report = controller.report
        if report["state"] not in ("Idle", "Run"):
            raise RuntimeError("Pomiar przerwany: " + report["state"])
        self._check_offset(controller)
        if report["state"] != "Idle":
            return
        position, machine = report["position"], report.get("MPos")
        if position is None or machine is None:
            return
        if self.state == "xy_wait":
            point = self.points[len(self.samples)]
            if abs(position[0] - point["x"]) > 0.01 or (
                abs(position[1] - point["y"]) > 0.01
                or abs(position[2] - self.clearance) > 0.01
                or report["probe_triggered"]
            ):
                raise RuntimeError("Niepoprawna pozycja lub styk przed próbą.")
            self.start_machine = machine[:]
            self.contact = None
            self.sampling = True
            self.distance = self.clearance + self.below
            self.deadline = (
                time.monotonic() + self.distance / self.feed * 60 + 8
            )
            self._write(controller,
                        f"G90G38.2Z{-self.below:g}F{self.feed:g}", "probing")
        elif self.state == "contact_wait":
            if any(abs(machine[i] - self.start_machine[i]) > 0.01
                   for i in (0, 1)) or not (
                -0.2 <= machine[2] - self.contact[2] <= 0.01
            ):
                raise RuntimeError("Niespójna pozycja po kontakcie.")
            height = self.contact[2] - self.reference
            if abs(height) > 1 or height >= self.clearance - 0.2:
                raise RuntimeError("Za duża różnica wysokości laminatu.")
            point = self.points[len(self.samples)]
            self.samples.append({**point, "z": height})
            self.deadline = time.monotonic() + 12
            self._write(controller, f"G0Z{self.clearance:g}", "retract_ack")
        elif self.state == "retract_wait":
            if abs(position[2] - self.clearance) > 0.01:
                return
            if report["probe_triggered"]:
                raise RuntimeError("Styk pozostał aktywny po odsunięciu.")
            if self.reference is None:
                if controller.offset is None:
                    return
                if abs(controller.offset[2] - self.contact[2]) > 0.002 or any(
                    abs(a - b) > 0.002 for a, b in zip(
                        controller.offset[:2], self.expected_xy_offset
                    )
                ):
                    raise RuntimeError("Nie potwierdzono zera referencyjnego.")
                self.reference = self.contact[2]
                self.offset = controller.offset[:]
            else:
                if any(abs(machine[i] - self.start_machine[i]) > 0.01
                       for i in (0, 1)):
                    raise RuntimeError("Zmiana X/Y podczas odsuwania.")
            self._next(controller)

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
