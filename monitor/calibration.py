# ---------------------------------------------------------------------------
# calibration.py
# 2026-10-24
# - Five-point service coupons using existing Z zero and guarded job runners.
# ---------------------------------------------------------------------------
"""Offline geometry, local probing and explicit cutting; never auto-start."""

import json
import copy
import math
import secrets
from pathlib import Path

from monitor.compensation import compensate_program, live_offset
from monitor.jobs import JobRunner, WORD, parse_program
from monitor.probes import ZProbe
from monitor.profiles import ProfileStore
from monitor.surfaces import MAX_PROBE_TRAVEL, SurfaceScan


def number(payload, key, low, high):
    """Reject malformed, nonfinite and out-of-range physical parameters."""
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Niepoprawny parametr: " + key)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{key}: zakres {low}–{high}.")
    return float(value)


def settings(payload):
    """Trial parameters; older profiles retain their 20 mm/min plunge feed."""
    if not isinstance(payload, dict):
        raise ValueError("Niepoprawny profil serwisowy.")
    return {
        "depth": number(payload, "depth", 0.01, 0.3),
        "width": number(payload, "width", 0.2, 2),
        "tip": number({"tip": payload.get("tip", 0.1)}, "tip", 0.01, 0.5),
        "angle": number({"angle": payload.get("angle", 30)},
                        "angle", 10, 90),
        "feed": number(payload, "feed", 10, 300),
        "plunge": number({"plunge": payload.get("plunge", 20)},
                         "plunge", 1, 100),
        "power": number(payload, "power", 1, 1000),
    }


def tool_diameter(config, depth):
    """Theoretical V groove width; angle is the full included tip angle."""
    profile = config.get("_calibration")
    if profile:
        model = profile["model"]
        if not model["min_depth"] - 1e-9 <= depth <= (
            model["max_depth"] + 1e-9
        ):
            raise ValueError("Głębokość poza zakresem kalibracji.")
        diameter = model["intercept_mm"] + model["slope"] * depth
        if diameter <= 0:
            raise ValueError("Profil przewiduje niedodatnią szerokość rowka.")
        return diameter
    tip = config.get("tip", 0.1)
    angle = config.get("angle", 30)
    return tip + 2 * depth * math.tan(math.radians(angle / 2))


def check_geometry(config):
    """Keep predicted tool sweep inside the fixed map and cuts separate."""
    diameter = tool_diameter(config, config["depth"])
    half = (config["width"] + diameter) / 2
    if 3.3 + half + diameter / 2 > 4.9 + 1e-9 or (
        3.3 - half - 1 - diameter < 0.1 - 1e-9
    ) or 1 - diameter < 0.1 - 1e-9:
        raise ValueError(
            "Próbka nie mieści się w polu 12 × 5 mm. Zmniejsz szerokość "
            "paska, zagłębienie lub wybierz inny frez."
        )


def coupon(origin, config):
    """A 10 mm groove and a closed contour around a nominal 10 mm strip.

    XY offsets use the current tool and depth. Subtracting that effective
    diameter from the contour centreline spacing leaves the requested strip.
    """
    x, y = origin
    check_geometry(config)
    diameter = tool_diameter(config, config["depth"])
    half = (config["width"] + diameter) / 2
    radius = diameter / 2
    lines = ["G21 G90 G94 G54", "M5", "G0 Z2",
             f"G0 X{x + 1:.4f} Y{y + 1:.4f}",
             f"M3 S{config['power']:g}", "G4 P2"]
    lines.extend([
        f"G1 Z{-config['depth']:.4f} F{config.get('plunge', 20):g}",
        f"G1 X{x + 11:.4f} F{config['feed']:g}", "G0 Z2",
        f"G0 X{x + 1 - radius:.4f} Y{y + 3.3 - half:.4f}",
        f"G1 Z{-config['depth']:.4f} F{config.get('plunge', 20):g}",
        f"G1 X{x + 11 + radius:.4f} F{config['feed']:g}",
        f"G1 Y{y + 3.3 + half:.4f}",
        f"G1 X{x + 1 - radius:.4f}",
        f"G1 Y{y + 3.3 - half:.4f}", "G0 Z2",
    ])
    lines.extend(["M5", "M30"])
    result = parse_program("service-coupon.nc", "\n".join(lines))
    result["tool_geometry"] = {
        "diameter_mm": diameter,
        "centreline_spacing_mm": config["width"] + diameter,
        "strip_width_mm": config["width"], "depth_mm": config["depth"],
        "correction": config.get("_calibration", {}).get("model"),
        "profile_id": config.get("_calibration", {}).get("id", "default"),
    }
    return result


def with_cut_depth(program, depth):
    """Apply an opted-in profile only to single-level, non-ramping PCB files."""
    number({"depth": depth}, "depth", 0.01, 0.3)
    levels = set()
    lines = []
    sources = []
    motion = None
    for original in program["lines"]:
        words = WORD.findall(original["code"])
        for letter, value in words:
            if letter == "G" and float(value) in (0, 1):
                motion = int(float(value))
        axes = {letter: float(value) for letter, value in words
                if letter in "XYZ"}
        if "Z" in axes and any(axis in axes for axis in "XY"):
            raise ValueError(
                "Profil Z wymaga pliku bez ramp i łączonych ruchów XYZ."
            )
        if axes.get("Z", 0) < 0:
            if motion != 1:
                raise ValueError("Profil Z nie obsługuje zagłębiania G0.")
            levels.add(axes["Z"])
        lines.append("".join(
            f"Z{-depth:.4f}" if letter == "Z" and float(value) < 0
            else letter + value for letter, value in words
        ))
        sources.append(original["source_line"])
    if len(levels) != 1:
        raise ValueError("Profil Z wymaga jednej ujemnej głębokości w pliku.")
    result = parse_program(program["name"], "\n".join(lines))
    result["cut_depth"] = depth
    for line in result["lines"]:
        line["source_line"] = sources[line["source_line"] - 1]
    return result


def five_height(surface, x, y):
    """Interpolate four triangles sharing the measured centre; no extrapolation."""
    points = surface.samples
    if not surface.valid or len(points) != 5:
        raise ValueError("Brak aktualnych pięciu punktów serwisowych.")
    for index in range(4):
        a, b, c = points[index], points[(index + 1) % 4], points[4]
        denominator = ((b["y"] - c["y"]) * (a["x"] - c["x"])
                       + (c["x"] - b["x"]) * (a["y"] - c["y"]))
        u = ((b["y"] - c["y"]) * (x - c["x"])
             + (c["x"] - b["x"]) * (y - c["y"])) / denominator
        v = ((c["y"] - a["y"]) * (x - c["x"])
             + (a["x"] - c["x"]) * (y - c["y"])) / denominator
        w = 1 - u - v
        if min(u, v, w) >= -0.00001:
            return u * a["z"] + v * b["z"] + w * c["z"]
    raise ValueError("Ruch poza lokalną mapą serwisową.")


class CalibrationScan(SurfaceScan):
    """Reuse bounded XY/probe/retract machinery without ever writing G10."""

    kind = "calibration"

    def start_local(self, controller, payload, origin, area_size=None):
        """Validate current position, raise, then touch exactly five points."""
        if controller.offset is None:
            raise ValueError("Brak aktualnego WCO.")
        position = controller.report.get("position")
        if position is None or not 0 <= position[2] <= 3:
            raise ValueError("Ustaw frez pomiędzy Z=0 a Z=3 mm.")
        # ZProbe supplies confirmation, probe-test, modal and fresh-position guards.
        result = ZProbe.start(self, controller, {
            **payload, "distance": MAX_PROBE_TRAVEL, "feed": 20,
        })
        if controller.offset is None:
            raise ValueError("Brak aktualnego WCO.")
        self.map_id = secrets.token_hex(12)
        self.job_id = None
        self.valid = False
        self.reason = None
        self.offset = controller.offset[:]
        self.reference = self.offset[2]
        self.reference_xy = origin[:]
        self.sampling = False
        self.clearance, self.below, self.feed = 1, 0.4, 20
        self.columns = self.rows = 2
        x, y = origin
        self.area = {"X": [x, x + 12], "Y": [y, y + 5]}
        self.points = [
            {"number": i + 1, "x": x + dx, "y": y + dy}
            for i, (dx, dy) in enumerate(
                [(0, 0), (12, 0), (12, 5), (0, 5), (6, 2.5)]
            )
        ]
        self.samples = []
        if area_size is not None:
            width, height = area_size
            self.kind = "profile_test"
            self.columns = self.rows = 3
            self.area = {"X": [x, x + width], "Y": [y, y + height]}
            self.points = []
            for row in range(3):
                columns = range(3) if row % 2 == 0 else range(2, -1, -1)
                for column in columns:
                    self.points.append({"number": len(self.points) + 1,
                                        "x": x + column * width / 2,
                                        "y": y + row * height / 2})
        else:
            self.kind = "calibration"
        return result

    def tick(self, controller):
        """The first command is a retract, never the reference-zero descent."""
        if self.state == "starting":
            # Let the shared tick handle expiry/cancellation before any write.
            self.command = "G0Z1"
        super().tick(controller)

    def _write(self, controller, command, state):
        if self.state == "starting" and command == "G0Z1":
            state = "retract_ack"
        super()._write(controller, command, state)

    def status(self):
        result = super().status()
        result["kind"] = self.kind
        return result


class Calibration:
    """Keep a coupon session separate from the uploaded production program."""

    def __init__(self, profile_path=None):
        self.scan = CalibrationScan()
        self.runner = JobRunner()
        self.session = None
        self.base = None
        self.origin = None
        self.config = None
        self.history = []
        self.pending = None
        self.mode = "service"
        self.profile_identity = None
        self.repeat_snapshot = None
        self.profile_path = profile_path or (
            Path.home() / ".local/share/bark-beetle/milling-profile.json"
        )
        self.profile = None
        self.profiles = ProfileStore(
            self.profile_path.with_name("calibration-profiles.json")
        )
        try:
            saved = json.loads(self.profile_path.read_text(encoding="utf-8"))
            self.profile = settings(saved)
        except (OSError, ValueError, TypeError):
            pass

    def status(self):
        self.observe()
        return {"session": self.session, "origin": self.origin, "mode": self.mode,
                "profile_identity": self.profile_identity,
                "base": self.base, "settings": self.config,
                "map": self.scan.status(), "job": self.runner.status(),
                "history": self.history, "profile": self.profile,
                "repeat": self.repeat_status()}

    def repeat_status(self):
        """Expose eligibility only; the captured execution stays server-side."""
        saved = self.repeat_snapshot
        if saved is None:
            return {"available": False, "valid": False, "passes": 0}
        complete = self.runner.state == "completed" and (
            self.runner.job_id == saved["job_id"]
        )
        return {"id": saved["id"], "valid": saved["valid"],
                "available": saved["valid"] and complete,
                "passes": saved["passes"], "reason": saved.get("reason"),
                "depth": saved["config"]["depth"]}

    def invalidate_repeat(self, reason):
        """A reset, zero/profile change or another operation forbids replay."""
        if self.repeat_snapshot is not None:
            self.repeat_snapshot.update(valid=False, reason=reason)

    def observe(self):
        """Record completion once, including aborted or uncertain trials."""
        state = self.runner.state
        if self.pending is not None and state in (
            "completed", "failed", "stopped"
        ):
            entry = {**self.pending, "state": state}
            self.history.append(entry)
            self.history = self.history[-50:]
            self.pending = None
            saved = self.repeat_snapshot
            if saved and saved["job_id"] == self.runner.job_id:
                if state == "completed" and saved["valid"]:
                    saved["passes"] += 1
                elif state != "completed":
                    self.invalidate_repeat("Przejazd nie został zakończony.")
            if state == "completed" and not entry.get("finish_pass"):
                try:
                    self.profiles.record(entry)
                except (OSError, ValueError) as error:
                    self.profiles.error = "Nie zapisano próby: " + str(error)

    def invalidate(self, reason):
        self.scan.invalidate(reason)
        self.invalidate_repeat(reason)

    def prepare(self, controller, payload, profile_test=False):
        """Lock the area before scanning; retries never reuse a touched field."""
        mode = "profile_test" if profile_test else "service"
        area_size = None
        if profile_test:
            from monitor.profile_test import configuration, layout

            config = configuration(self.profiles, payload)
            plan = layout(config)
            area_size = (plan["width"], plan["height"])
        else:
            config = settings(payload)
            check_geometry(config)
        controller._status()
        if payload.get("session") != self.session:
            raise ValueError("Sesja serwisowa zmieniła się.")
        if payload.get("new_session") is True or self.base is None or (
            mode != self.mode
        ):
            base = controller.report.get("position")
            if base is None:
                raise ValueError("Brak pozycji CNC.")
            base = base[:2]
            used = 0
        else:
            base = self.base[:]
            # Consume the previous area even after a stopped scan or partial cut.
            used = self.index + 1
        if used >= 50:
            raise ValueError("Rozpocznij nową sesję na świeżym laminacie.")
        width, height = area_size or (12, 5)
        origin = [base[0], base[1] + used * (height + 1.5)]
        if not (-300 <= origin[0] <= 300 - width
                and -180 <= origin[1] <= 180 - height):
            raise ValueError("Pole serwisowe przekracza dopuszczalny zakres.")
        result = self.scan.start_local(controller, payload, origin, area_size)
        self.invalidate_repeat("Rozpoczęto nowy pomiar lub próbę.")
        self.session = secrets.token_hex(12)
        if payload.get("new_session") is True:
            self.history = []
        self.base, self.origin, self.index = base, origin, used
        self.config = config
        self.mode = mode
        self.profile_identity = ({"id": self.profiles.active["id"],
                                  "fingerprint": self.profiles.active[
                                      "fingerprint"]} if profile_test else None)
        controller.last_probe = self.scan
        return result

    def cut(self, controller, payload, profile_test=False):
        """Require a fresh map, matching zero, position and separate confirmation."""
        if self.mode != ("profile_test" if profile_test else "service"):
            raise ValueError("Mapa pochodzi z innego trybu; powtórz pomiar.")
        if payload.get("confirmed") is not True or (
            payload.get("clip_removed") is not True
        ):
            raise ValueError("Potwierdź zdjęcie krokodylka z frezu.")
        if payload.get("session") != self.session or (
            payload.get("map_id") != self.scan.map_id or not self.scan.valid
        ):
            raise ValueError("Wykonaj aktualny pomiar pięciu punktów.")
        controller._status()
        if controller.report["state"] != "Idle" or (
            controller.report["probe_triggered"]
        ):
            raise ValueError("Wymagane Idle i rozwarty styk sondy.")
        expected = payload.get("position")
        position = controller.report.get("position")
        if not isinstance(expected, list) or len(expected) != 3 or (
            position is None or any(
                not isinstance(v, (int, float)) or isinstance(v, bool)
                or not math.isfinite(v) or abs(v - p) > 0.002
                for v, p in zip(expected, position)
            )
        ):
            raise ValueError("Pozycja zmieniła się; potwierdź ponownie.")
        modal = controller._line("$G")
        if not any(line.startswith("[GC:") and line.endswith("]")
                   and {"G54", "G21", "G90", "G94", "M5"}.issubset(
                       line[4:-1].split()) for line in modal):
            raise ValueError("Wymagane G54 G21 G90 G94 M5.")
        offset = live_offset(controller._line("$#"))
        if any(abs(a - b) > 0.002 for a, b in zip(offset, self.scan.offset)):
            self.invalidate("Zero zmieniło się.")
            raise ValueError("Zero mapy zmieniło się; powtórz pomiar.")
        if profile_test:
            from monitor.profile_test import configuration, program as build

            config = configuration(self.profiles, payload)
        else:
            config = settings(payload)
            build = coupon
        before = self.config.get("_calibration", {}).get("fingerprint")
        if config.get("_calibration", {}).get("fingerprint") != before:
            raise ValueError("Profil zmienił się; powtórz pomiar Z.")
        if any(config[key] != self.config.get(key, default)
               for key, default in (("tip", 0.1), ("angle", 30))):
            raise ValueError("Frez zmienił się; wykonaj nowy pomiar Z.")
        program = compensate_program(
            build(self.origin, config), self.scan,
            approach_mm=0.5 if profile_test else None,
        )
        self.runner.load(program)
        result = self.runner.start(self.runner.job_id)
        self.pending = {"number": self.index + 1, "origin": self.origin[:],
                        "mode": self.mode,
                        **settings(config), "trial_id": secrets.token_hex(12),
                        "geometry": program["tool_geometry"]}
        self.config = config
        self.scan.invalidate("Pole wykorzystane; nowy test wymaga świeżej mapy.")
        if profile_test:
            self.repeat_snapshot = {
                "id": secrets.token_hex(12), "valid": True, "passes": 0,
                "job_id": self.runner.job_id, "session": self.session,
                "config": copy.deepcopy(config),
                "profile": copy.deepcopy(self.profile_identity),
                "program": copy.deepcopy(program),
                "offset": self.scan.offset[:],
                "area": copy.deepcopy(self.scan.area),
            }
        return result

    def finish(self, controller, payload):
        """Manually replay one completed test without recompensating its Z."""
        self.observe()
        saved = self.repeat_snapshot
        if not self.repeat_status()["available"] or saved is None or (
            payload.get("repeat_id") != saved["id"]
            or payload.get("session") != saved["session"]
        ):
            raise ValueError("Brak aktualnego, zakończonego testu do powtórki.")
        if payload.get("confirmed") is not True or (
            payload.get("setup_unchanged") is not True
            or payload.get("clip_removed") is not True
        ):
            raise ValueError("Potwierdź niezmieniony frez, laminat, "
                             "mocowanie i zdjęcie przewodu sondy.")
        from monitor.profile_test import configuration

        config = configuration(self.profiles, payload)
        if config != saved["config"]:
            self.invalidate_repeat("Parametry profilu zmieniły się.")
            raise ValueError("Profil nie odpowiada zapisanemu testowi.")
        controller._status()
        report = controller.report
        position = report.get("position")
        expected = payload.get("position")
        if report["state"] != "Idle" or report["probe_triggered"]:
            raise ValueError("Powtórka wymaga Idle i rozwartej sondy.")
        if not isinstance(expected, list) or len(expected) != 3 or (
            position is None or any(
                not isinstance(value, (int, float)) or isinstance(value, bool)
                or not math.isfinite(value) or abs(value - actual) > .002
                for value, actual in zip(expected, position)
            )
        ):
            raise ValueError("Pozycja zmieniła się; potwierdź ponownie.")
        area = saved["area"]
        if not (area["X"][0] - .002 <= position[0] <= area["X"][1] + .002
                and area["Y"][0] - .002 <= position[1] <= area["Y"][1] + .002
                and 0 <= position[2] <= 3):
            raise ValueError("Ustaw frez nad zapisanym polem testu, Z 0–3 mm.")
        modal = controller._line("$G")
        if not any(line.startswith("[GC:") and line.endswith("]")
                   and {"G54", "G21", "G90", "G94", "M5"}.issubset(
                       line[4:-1].split()) for line in modal):
            raise ValueError("Wymagane G54 G21 G90 G94 M5.")
        offset = live_offset(controller._line("$#"))
        if any(abs(a - b) > .002 for a, b in zip(offset, saved["offset"])):
            self.invalidate_repeat("Zero zmieniło się; powtórz przygotowanie.")
            raise ValueError("Zero nie odpowiada zapisanemu testowi.")
        # The captured program already includes local Z compensation once.
        self.runner.load(copy.deepcopy(saved["program"]))
        result = self.runner.start(self.runner.job_id)
        saved["job_id"] = self.runner.job_id
        self.pending = {"number": self.index + 1, "origin": self.origin[:],
                        "mode": "profile_test", "finish_pass": True,
                        "pass_number": saved["passes"] + 1,
                        **settings(config),
                        "geometry": saved["program"]["tool_geometry"]}
        return result

    def save(self, payload):
        """Persist only an actually completed trial, never a claimed tool diameter."""
        self.observe()
        entry = next((entry for entry in reversed(self.history)
                      if entry["number"] == payload.get("number")
                      and entry["state"] == "completed"), None)
        if entry is None or payload.get("session") != self.session:
            raise ValueError("Wybierz zakończoną próbę z bieżącej sesji.")
        profile = settings(entry)
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.profile_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(profile) + "\n", encoding="utf-8")
        temporary.replace(self.profile_path)
        self.profile = profile

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
