# ---------------------------------------------------------------------------
# profiles.py
# 2026-10-24
# - Persistent measured tool profiles, explicit selection and CAM contracts.
# ---------------------------------------------------------------------------
"""Tool-width calibration affects generated paths, never machine axis scales."""

import copy
import hashlib
import json
import math
import secrets

from monitor.jobs import WORD


CONDITIONS = ("tip", "angle", "feed", "plunge", "power")
DEFAULT = {"id": "default", "name": "Domyślny", "model": None,
           "fingerprint": "default", "depth": .05,
           "conditions": {"tip": .1, "angle": 30, "feed": 100,
                          "plunge": 20, "power": 300}}


def finite(value):
    """Accept real JSON numbers only."""
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def fit_profile(rows):
    """Infer effective diameter from the strip left between two tool passes.

    Using the diameter actually used to generate each trial avoids applying
    an existing correction twice. One observation offsets the nominal V model;
    multiple observations fit D(h) = a + b*h with least squares.
    """
    if not 1 <= len(rows) <= 8:
        raise ValueError("Podaj od 1 do 8 pomiarów.")
    conditions = {key: rows[0][key] for key in CONDITIONS}
    points = []
    for index, row in enumerate(rows, 1):
        if any(row[key] != conditions[key] for key in CONDITIONS):
            raise ValueError("Próby muszą mieć ten sam frez, posuwy i S.")
        measured = row.get("measured_width")
        depth = row.get("depth")
        used = row.get("geometry", {}).get("diameter_mm")
        width = row.get("width")
        if not all(finite(v) for v in (measured, depth, used, width)):
            raise ValueError("Brak poprawnego pomiaru lub geometrii próby.")
        diameter = used + width - measured
        if not 0.01 <= measured <= 3 or not 0 < diameter < 2:
            raise ValueError(
                f"Pomiar {index}: wyliczony rowek {diameter:.4f} mm jest "
                "niepoprawny. Sprawdź nominalny pasek (ustawienie próbki), "
                "zmierzony pasek i rowek użyty w programie."
            )
        if not 0.01 <= depth <= 0.3:
            raise ValueError("Niepoprawne zagłębienie próby.")
        points.append((depth, diameter))
    depths = [point[0] for point in points]
    if len(points) == 1:
        angle = conditions["angle"]
        tip = conditions["tip"]
        if not finite(angle) or not 10 <= angle <= 90 or (
            not finite(tip) or not .01 <= tip <= .5
        ):
            raise ValueError("Niepoprawna geometria frezu.")
        slope = 2 * math.tan(math.radians(angle / 2))
        depth, diameter = points[0]
        intercept = diameter - slope * depth
        return {"conditions": conditions, "model": {
            "kind": "single_offset", "intercept_mm": intercept,
            "slope": slope, "offset_mm": intercept - tip,
            "reference_depth": depth, "min_depth": .01,
            "max_depth": .3, "rmse_mm": None,
        }}
    if max(depths) - min(depths) < 0.01 - 1e-9:
        raise ValueError("Potrzebne dwa zagłębienia różniące się ≥0,01 mm.")
    mean_x = sum(depths) / len(points)
    mean_y = sum(point[1] for point in points) / len(points)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points)
    slope /= sum((x - mean_x) ** 2 for x, y in points)
    intercept = mean_y - slope * mean_x
    if slope <= 0:
        raise ValueError("Rowek nie rośnie z głębokością; powtórz pomiary.")
    residual = math.sqrt(sum((y - intercept - slope * x) ** 2
                             for x, y in points) / len(points))
    return {"conditions": conditions,
            "model": {"intercept_mm": intercept, "slope": slope,
                      "min_depth": min(depths), "max_depth": max(depths),
                      "rmse_mm": residual}}


def fingerprint(profile):
    """Stable identity of immutable exported calibration data."""
    data = {key: value for key, value in profile.items()
            if key != "fingerprint"}
    return hashlib.sha256(json.dumps(
        data, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()


def validate_depth(depth, model):
    """A profile pins one cut depth; older exports remain immutable."""
    if not finite(depth) or not .01 <= depth <= .3 or not (
        model["min_depth"] - 1e-9 <= depth <= model["max_depth"] + 1e-9
    ) or model["intercept_mm"] + model["slope"] * depth <= 0:
        raise ValueError("Głębokość profilu poza zakresem modelu: "
                         "wpisz poprawną wartość 0,01–0,3 mm.")


def manual_observations(payload, samples):
    """Accept explicit measurements without requiring recorded trial output.

    The supplied CAM diameter is evidence, not a hidden correction. If absent,
    use the nominal V-tool formula, suitable for trials made with Default.
    """
    conditions = {}
    limits = {"tip": (.01, .5), "angle": (10, 90), "feed": (10, 300),
              "plunge": (1, 100), "power": (1, 1000)}
    for key, (low, high) in limits.items():
        value = payload.get(key)
        if not finite(value) or not low <= value <= high:
            raise ValueError(f"{key}: wpisz wartość {low}–{high}.")
        conditions[key] = float(value)
    rows = []
    for index, sample in enumerate(samples, 1):
        if not isinstance(sample, dict):
            raise ValueError("Niepoprawny pomiar ręczny.")
        depth = sample.get("depth")
        width = sample.get("width")
        if not finite(depth) or not .01 <= depth <= .3 or (
            not finite(width) or not .2 <= width <= 2
        ):
            raise ValueError(f"Pomiar {index}: zagłębienie 0,01–0,3 mm; "
                             "nominalny pasek 0,2–2 mm.")
        used = sample.get("used_diameter")
        if used is None:
            used = conditions["tip"] + 2 * depth * math.tan(
                math.radians(conditions["angle"] / 2)
            )
        if not finite(used) or not .001 <= used < 2:
            raise ValueError(f"Pomiar {index}: niepoprawny rowek w programie.")
        rows.append({**conditions, "depth": float(depth), "width": float(width),
                     "measured_width": sample.get("measured_width"),
                     "geometry": {"diameter_mm": float(used)},
                     "source": "manual"})
    return rows


def check_cam_program(active, program, payload):
    """Check declared CAM provenance and observable cutting parameters.

    A marker is an operator declaration; geometry cannot prove which tool
    diameter CAM used. It never causes post-hoc XY transformations.
    """
    marker = program.get("cam_profile")
    if active["id"] == "default" and marker is None:
        return
    if marker != {"id": active["id"],
                  "fingerprint": active["fingerprint"]}:
        raise ValueError("Profil pliku NC nie odpowiada aktywnemu "
                         "profilowi. Oblicz CAM ponownie w kolekcji RPi.")
    if payload.get("service_depth") is True or "xy_feed" in payload:
        raise ValueError("Profil kalibracji wymaga głębokości i "
                         "posuwów z CAM; wyłącz nadpisywanie.")
    depth = -program["bounds_mm"]["Z"][0]
    model = active["model"]
    conditions = active["conditions"]
    if "depth" in active and abs(depth - active["depth"]) > 1e-6:
        raise ValueError("Zagłębienie NC nie odpowiada stałej głębokości "
                         "profilu; wygeneruj CAM ponownie.")
    if not model["min_depth"] - 1e-6 <= depth <= (
        model["max_depth"] + 1e-6
    ) or program["max_power"] != conditions["power"] or any(
        feed != conditions["plunge"]
        for feed in program.get("z_feeds", [])
    ):
        raise ValueError("Parametry NC nie odpowiadają profilowi.")
    if model["intercept_mm"] + model["slope"] * depth <= 0:
        raise ValueError("Profil przewiduje niedodatnią szerokość rowka.")
    motion = None
    feed = None
    for line in program["lines"]:
        words = WORD.findall(line["code"])
        for letter, value in words:
            if letter == "G" and float(value) in (0, 1):
                motion = int(float(value))
            if letter == "F":
                feed = float(value)
            if letter == "S" and float(value) not in (
                0, conditions["power"]
            ):
                raise ValueError("Wartość S w NC nie odpowiada profilowi.")
        axes = {key for key, value in words if key in "XYZ"}
        if "depth" in active and any(
            key == "Z" and float(value) < 0
            and abs(float(value) + active["depth"]) > 1e-6
            for key, value in words
        ):
            raise ValueError("Wszystkie poziomy cięcia muszą odpowiadać "
                             "głębokości profilu.")
        if motion == 1 and axes.intersection("XY"):
            if feed != conditions["feed"] or "Z" in axes:
                raise ValueError("Profil wymaga zgodnego posuwu XY "
                                 "i pliku bez ramp XYZ.")


class ProfileStore:
    """Persist profiles and completed trials without touching CNC hardware."""

    def __init__(self, path):
        self.path = path
        self.data = {"version": 1, "active": "default", "profiles": [],
                     "trials": []}
        self.error = None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("version") != 1 or not isinstance(
                data.get("profiles"), list
            ) or not isinstance(data.get("trials"), list):
                raise ValueError("Niepoprawny format profili.")
            for profile in data["profiles"]:
                if profile["fingerprint"] != fingerprint(profile):
                    raise ValueError("Niepoprawna suma kontrolna profilu.")
                fitted = fit_profile(profile["observations"])
                if any(profile[key] != fitted[key]
                       for key in ("conditions", "model")):
                    raise ValueError("Niespójne dane kalibracji.")
                if "depth" in profile:
                    validate_depth(profile["depth"], profile["model"])
            if data.get("active") not in ["default"] + [
                profile["id"] for profile in data["profiles"]
            ]:
                raise ValueError("Brak aktywnego profilu.")
            self.data = data
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, KeyError) as error:
            self.error = "Nie można odczytać profili: " + str(error)

    @property
    def active(self):
        return next((item for item in self.data["profiles"]
                     if item["id"] == self.data["active"]), DEFAULT)

    def status(self):
        """Return a copy so request handlers cannot mutate stored evidence."""
        public = {key:value for key,value in self.data.items()
                  if key != "revisions"}
        return copy.deepcopy({**public, "error": self.error,
                              "selected": self.active,
                              "profiles": [DEFAULT] + self.data["profiles"]})

    def _commit(self, data):
        if self.error:
            raise ValueError(self.error + "; przywróć plik z kopii.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, allow_nan=False) + "\n",
                             encoding="utf-8")
        temporary.replace(self.path)
        self.data = data

    def record(self, entry):
        """Only the runner's completed observation may become fit evidence."""
        data = copy.deepcopy(self.data)
        data["trials"] = (data["trials"] + [entry])[-100:]
        self._commit(data)

    def _build(self, payload):
        """Accept manual observations or resolve recorded trial IDs."""
        name = payload.get("name")
        samples = payload.get("samples")
        if not isinstance(name, str) or not (
            1 <= len(name.strip()) <= 40
        ):
            raise ValueError("Nazwa profilu: 1–40 znaków.")
        if any(ord(char) < 32 for char in name):
            raise ValueError("Niepoprawna nazwa profilu.")
        if not isinstance(samples, list) or not 1 <= len(samples) <= 8:
            raise ValueError("Podaj od 1 do 8 pomiarów.")
        rows = []
        if payload.get("source") == "manual":
            rows = manual_observations(payload, samples)
        ids = set()
        for sample in ([] if rows else samples):
            if not isinstance(sample, dict):
                raise ValueError("Niepoprawny pomiar.")
            trial_id = sample.get("trial_id")
            trial = next((item for item in self.data["trials"]
                          if item["trial_id"] == trial_id), None)
            if trial is None or trial_id in ids:
                raise ValueError("Wybierz różne zakończone próby.")
            ids.add(trial_id)
            rows.append({**trial,
                         "measured_width": sample.get("measured_width")})
        fitted = fit_profile(rows)
        depth = payload.get("depth", rows[0]["depth"])
        validate_depth(depth, fitted["model"])
        profile = {"id": secrets.token_hex(8), "name": name.strip(),
                   **fitted, "observations": rows, "depth": float(depth)}
        revision = payload.get("revision_of")
        if revision is not None:
            if not any(item["id"] == revision
                       for item in self.data["profiles"]):
                raise ValueError("Brak źródłowego profilu wersji.")
            profile["revision_of"] = revision
        profile["fingerprint"] = fingerprint(profile)
        return profile

    def create(self, payload):
        """Persist a new named profile without changing the selected one."""
        if len(self.data["profiles"]) >= 30:
            raise ValueError("Limit 30 profili; usuń nieużywany profil.")
        profile = self._build(payload)
        data = copy.deepcopy(self.data)
        data["profiles"].append(profile)
        self._commit(data)
        return profile

    def update(self, payload):
        """Edit one profile atomically; retain previous data outside the UI."""
        previous = next((item for item in self.data["profiles"]
                         if item["id"] == payload.get("profile_id")), None)
        if previous is None:
            raise ValueError("Wybierz edytowalny profil.")
        if payload.get("profile_fingerprint") != previous["fingerprint"]:
            raise ValueError("Profil został zmieniony; odśwież ustawienia.")
        profile = self._build({**payload, "revision_of": previous["id"]})
        profile["id"] = previous["id"]
        profile["revision"] = previous.get("revision", 1) + 1
        profile["fingerprint"] = fingerprint(profile)
        data = copy.deepcopy(self.data)
        data["revisions"] = (data.get("revisions", []) + [previous])[-100:]
        data["profiles"] = [profile if item["id"] == previous["id"] else item
                            for item in data["profiles"]]
        self._commit(data)
        return profile

    def select(self, profile_id):
        """Selection is explicit and retained after a service restart."""
        if profile_id not in ["default"] + [
            item["id"] for item in self.data["profiles"]
        ]:
            raise ValueError("Profil nie istnieje.")
        data = copy.deepcopy(self.data)
        data["active"] = profile_id
        self._commit(data)

    def delete(self, profile_id):
        """Deleting an active profile explicitly returns selection to Default."""
        if profile_id == "default":
            raise ValueError("Nie można usunąć profilu Domyślnego.")
        data = copy.deepcopy(self.data)
        if data["active"] == profile_id:
            data["active"] = "default"
        data["profiles"] = [item for item in data["profiles"]
                            if item["id"] != profile_id]
        self._commit(data)

    def resolve(self, config, payload):
        """Bind current UI parameters to the exact active calibration model."""
        if self.error:
            raise ValueError(self.error)
        active = self.active
        if payload.get("profile_id", "default") != active["id"] or (
            active["model"] and payload.get("profile_fingerprint")
            != active["fingerprint"]
        ):
            raise ValueError("Profil zmienił się; odśwież ustawienia.")
        if not active["model"]:
            return config
        if any(config[key] != value
               for key, value in active["conditions"].items()):
            raise ValueError("Frez, posuwy i S muszą odpowiadać profilowi.")
        model = active["model"]
        if "depth" in active and abs(config["depth"] - active["depth"]) > 1e-9:
            raise ValueError("Zagłębienie jest stałym parametrem profilu.")
        if not model["min_depth"] - 1e-9 <= config["depth"] <= (
            model["max_depth"] + 1e-9
        ):
            raise ValueError("Zagłębienie poza zmierzonym zakresem profilu.")
        if model["intercept_mm"] + model["slope"] * config["depth"] <= 0:
            raise ValueError("Profil przewiduje niepoprawną szerokość rowka "
                             "przy tym zagłębieniu.")
        return {**config, "_calibration": copy.deepcopy(active)}

    def check_program(self, program, payload):
        """A finished file must already contain XY generated by matching CAM."""
        if self.error:
            raise ValueError(self.error)
        check_cam_program(self.active, program, payload)

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
