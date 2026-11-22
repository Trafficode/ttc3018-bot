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
from datetime import datetime, timezone

from monitor.jobs import WORD


CONDITIONS = ("tip", "angle", "feed", "plunge", "power")
CONDITION_LIMITS = {"tip": (.01, .5), "angle": (10, 90), "feed": (10, 300),
                    "plunge": (1, 100), "power": (1, 1000)}
GROOVE_AGREEMENT_MM = .02
DEFAULT = {"id": "default", "name": "Domyślny", "model": None,
           "fingerprint": "default", "depth": .05,
           "conditions": {"tip": .1, "angle": 30, "feed": 100,
                          "plunge": 20, "power": 300}}


def finite(value):
    """Accept real JSON numbers only."""
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def strip_diameter(row):
    measured = row.get("measured_width")
    used = row.get("geometry", {}).get("diameter_mm")
    width = row.get("width")
    if not all(finite(value) for value in (measured, used, width)):
        raise ValueError("Brak poprawnego pomiaru lub geometrii próby.")
    diameter = used + width - measured
    if not .01 <= measured <= 3 or not 0 < diameter < 2:
        raise ValueError(
            f"Wyliczony rowek {diameter:.4f} mm jest niepoprawny. "
            "Sprawdź nominalny i zmierzony pasek oraz rowek użyty w programie."
        )
    return diameter


def measured_groove_diameter(measurement, geometry):
    if not isinstance(measurement, dict):
        raise ValueError("Brak pomiaru rowka.")
    total, step = measurement.get("total_mm"), measurement.get("step_mm")
    if not finite(total) or not .01 <= total <= 3 or not finite(step) or (
        step < 0 or step != geometry.get("step_mm")
    ):
        raise ValueError("Pomiar rowka nie odpowiada geometrii próby.")
    diameter = total - step
    if not step + 1e-9 < diameter < 2:
        raise ValueError("Rowek jest poza zakresem lub przejazdy nie zachodzą na siebie.")
    return diameter


def fit_profile(rows):
    """Fit the effective diameter using the selected measurement for each trial.

    Using the diameter actually used to generate each trial avoids applying
    an existing correction twice. One observation offsets the nominal V model;
    multiple observations fit D(h) = a + b*h with least squares.
    """
    if not 1 <= len(rows) <= 8:
        raise ValueError("Podaj od 1 do 8 pomiarów.")
    conditions = {key: rows[0][key] for key in CONDITIONS}
    points = []
    for row in rows:
        if any(row[key] != conditions[key] for key in CONDITIONS):
            raise ValueError("Próby muszą mieć ten sam frez, posuwy i S.")
        depth = row.get("depth")
        method = row.get("calibration_method")
        if method == "groove":
            diameter = measured_groove_diameter(row.get("groove_measurement"), row["geometry"])
        elif method in (None, "strip"):
            diameter = strip_diameter(row)
        else:
            raise ValueError("Nieznana metoda kalibracji.")
        if not finite(depth) or not 0.01 <= depth <= 0.3:
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


def groove_evidence(profile):
    """Bind the operator's measurement to all calibration inputs, not a name."""
    return {"depth": profile["depth"], "conditions": profile["conditions"],
            "samples": [{**({"groove_measurement": row["groove_measurement"]}
                            if "groove_measurement" in row else {}),
                         **({"calibration_method": row["calibration_method"]}
                            if "calibration_method" in row else {}),
                         "depth": row["depth"], "width": row["width"],
                         **({"measured_width": row["measured_width"]}
                            if "measured_width" in row else {}),
                         **({"corner_feed_mm_min": row["geometry"]["corner_feed_mm_min"]}
                            if "corner_feed_mm_min" in row["geometry"] else {}),
                         "used_diameter": row["geometry"]["diameter_mm"]}
                        for row in profile["observations"]]}


def groove_width(profile):
    return profile["model"]["intercept_mm"] + (
        profile["model"]["slope"] * profile["depth"])


def validate_groove_confirmation(profile, confirmation):
    """A checkbox attests an exact width; it must never alter the tool model."""
    if any(row.get("calibration_method") == "strip" for row in profile["observations"]):
        raise ValueError("Pomiar paska nie potwierdza pomiaru rowka.")
    if not isinstance(confirmation, dict) or confirmation.get(
        "evidence") != groove_evidence(profile) or not finite(
            confirmation.get("diameter_mm")) or not math.isclose(
                confirmation["diameter_mm"], groove_width(profile),
                rel_tol=0, abs_tol=1e-8):
        raise ValueError("Dane kalibracji zmieniły się. Ponownie zmierz "
                         "rowek i potwierdź aktualny wynik.")


def validate_depth(depth, model):
    """A profile pins one cut depth; older exports remain immutable."""
    if not finite(depth) or not .01 <= depth <= .3 or not (
        model["min_depth"] - 1e-9 <= depth <= model["max_depth"] + 1e-9
    ) or model["intercept_mm"] + model["slope"] * depth <= 0:
        raise ValueError("Głębokość profilu poza zakresem modelu: "
                         "wpisz poprawną wartość 0,01–0,3 mm.")


def validate_corner_feed(value, straight_feed):
    if value is not None and (not finite(value) or not 1 <= value <= straight_feed):
        raise ValueError("Posuw na zakrętach: od 1 mm/min do posuwu XY.")


def profile_settings(payload):
    name = payload.get("name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 40:
        raise ValueError("Nazwa profilu: 1–40 znaków.")
    if any(ord(char) < 32 for char in name):
        raise ValueError("Niepoprawna nazwa profilu.")
    depth = payload.get("depth")
    if not finite(depth) or not .01 <= depth <= .3:
        raise ValueError("Zagłębienie: zakres 0,01–0,3 mm.")
    conditions = cutting_conditions(payload)
    corner_feed = payload.get("corner_feed")
    validate_corner_feed(corner_feed, conditions["feed"])
    result = {"name": name.strip(), "depth": float(depth), "conditions": conditions}
    if corner_feed is not None:
        result["corner_feed"] = float(corner_feed)
    return result


def cutting_conditions(payload):
    conditions = {}
    for key, (low, high) in CONDITION_LIMITS.items():
        value = payload.get(key)
        if not finite(value) or not low <= value <= high:
            raise ValueError(f"{key}: wpisz wartość {low}–{high}.")
        conditions[key] = float(value)
    return conditions


def manual_observations(payload, samples):
    """Accept explicit measurements without requiring recorded trial output.

    The supplied CAM diameter is evidence, not a hidden correction. If absent,
    use the nominal V-tool formula, suitable for trials made with Default.
    """
    conditions = cutting_conditions(payload)
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
    if active.get("draft"):
        raise ValueError("Szkic profilu służy tylko do testu; wybierz profil CAM.")
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
    z = None
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
        axes = {key: float(value) for key, value in words if key in "XYZ"}
        if "depth" in active and any(
            key == "Z" and float(value) < 0
            and abs(float(value) + active["depth"]) > 1e-6
            for key, value in words
        ):
            raise ValueError("Wszystkie poziomy cięcia muszą odpowiadać "
                             "głębokości profilu.")
        target_z = axes.get("Z", z)
        level_above_surface = z == target_z and (target_z or 0) > 0
        if motion == 1 and ("X" in axes or "Y" in axes) and not level_above_surface:
            if feed != conditions["feed"] or "Z" in axes:
                raise ValueError("Profil wymaga zgodnego posuwu XY "
                                 "i pliku bez ramp XYZ.")
        z = target_z


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
                validate_corner_feed(profile.get("corner_feed"), profile["conditions"]["feed"])
                if profile.get("draft") is True:
                    profile_settings({**profile, **profile["conditions"]})
                    if profile["model"] is not None or profile["observations"]:
                        raise ValueError("Szkic nie może zawierać modelu.")
                    continue
                fitted = fit_profile(profile["observations"])
                if any(profile[key] != fitted[key]
                       for key in ("conditions", "model")):
                    raise ValueError("Niespójne dane kalibracji.")
                if "depth" in profile:
                    validate_depth(profile["depth"], profile["model"])
                if profile.get("groove_verification") is not None:
                    validate_groove_confirmation(
                        profile, profile["groove_verification"])
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
        confirmation = payload.get("groove_confirmation")
        if confirmation is not None:
            validate_groove_confirmation(profile, confirmation)
            profile["groove_verification"] = {
                "evidence": groove_evidence(profile),
                "diameter_mm": groove_width(profile),
                "confirmed_at": datetime.now(timezone.utc).isoformat()}
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
        profile = ({"id": secrets.token_hex(8), **profile_settings(payload),
                    "draft": True, "model": None, "observations": []}
                   if payload.get("source") == "settings" else self._build(payload))
        profile["fingerprint"] = fingerprint(profile)
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
        source = payload.get("source")
        if source == "settings":
            settings = profile_settings({"corner_feed": previous.get("corner_feed"), **payload})
            corner_feed = settings.get("corner_feed")
            if previous.get("corner_feed") == corner_feed and all(
                previous.get(key) == value for key, value in settings.items()
            ):
                return copy.deepcopy(previous)
            if all(previous.get(key) == settings[key] for key in ("depth", "conditions")):
                profile = {**previous, **settings}
                if corner_feed is None:
                    profile.pop("corner_feed", None)
            else:
                profile = {**settings, "draft": True, "model": None, "observations": []}
        elif source == "profile_test":
            profile = self._from_profile_test(previous, payload)
        else:
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

    def _from_profile_test(self, previous, payload):
        """Use the selected operator measurement from the matching completed trial."""
        if payload.get("confirmed") is not True:
            raise ValueError("Potwierdź własny pomiar kalibracyjny.")
        identity = {key: previous[key] for key in ("id", "fingerprint")}
        trial = next((row for row in reversed(self.data["trials"])
                      if row.get("mode") == "profile_test"
                      and row.get("state") == "completed"
                      and row.get("profile") == identity), None)
        if not trial or trial["trial_id"] != payload.get("trial_id"):
            raise ValueError("Wybierz ostatni zakończony test dla tych ustawień.")
        geometry = trial["geometry"]
        method = payload.get("calibration_method")
        legacy = "calibration_method" not in payload
        if not legacy and method not in ("strip", "groove"):
            raise ValueError("Wybierz metodę: z paska albo z rowka.")
        strip = payload.get("measured_width")
        total = payload.get("measured_groove")
        if ((legacy or method == "strip") and strip is None) or (
            (legacy or method == "groove") and total is None
        ):
            raise ValueError("Wpisz pomiar dla wybranej metody.")
        for value in (strip, total):
            if value is None:
                continue
            if not finite(value) or not .01 <= value <= 3 or not math.isclose(
                value * 100, round(value * 100), rel_tol=0, abs_tol=1e-7
            ):
                raise ValueError("Wpisz pomiar z krokiem 0,01 mm.")
        strip_data, groove_data = {}, {}
        inferred = measured_single = None
        if strip is not None:
            width = payload.get("width")
            if not finite(width) or width not in geometry["strip_widths"]:
                raise ValueError("Wybierz pasek z wykonanego testu.")
            strip_data = {"width": width, "measured_width": strip}
            inferred = strip_diameter({**trial, **strip_data})
        if total is not None:
            step = geometry["step_mm"]
            measurement = {"total_mm": total, "step_mm": step}
            measured_single = measured_groove_diameter(measurement, geometry)
            if method == "groove" and step > 0 and payload.get("groove_continuous") is not True:
                raise ValueError("Potwierdź, że oba przejazdy tworzą jeden ciągły rowek.")
            groove_data = {"groove_measurement": measurement}
        if inferred is not None and measured_single is not None and not math.isclose(
            measured_single, inferred, rel_tol=0, abs_tol=GROOVE_AGREEMENT_MM + 1e-9
        ) and (legacy or payload.get("accept_disagreement") is not True):
            raise ValueError("Pomiary są rozbieżne. Potwierdź użycie wybranej metody.")
        if legacy:
            observation = {**trial, **strip_data, **groove_data}
        else:
            observation = {**trial, "calibration_method": method,
                           **(strip_data if method == "strip" else groove_data)}
        profile = {"name": previous["name"], **fit_profile([observation]),
                   "observations": [observation], "depth": trial["depth"]}
        if "corner_feed" in previous:
            profile["corner_feed"] = previous["corner_feed"]
        validate_depth(profile["depth"], profile["model"])
        if legacy or method == "groove":
            profile["groove_verification"] = {
                "evidence": groove_evidence(profile), "diameter_mm": groove_width(profile),
                "confirmed_at": datetime.now(timezone.utc).isoformat()}
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

    def resolve(self, config, payload, *, allow_draft=False):
        """Bind current UI parameters to the exact active calibration model."""
        if self.error:
            raise ValueError(self.error)
        active = self.active
        if payload.get("profile_id", "default") != active["id"] or (
            active["model"] and payload.get("profile_fingerprint")
            != active["fingerprint"]
        ):
            raise ValueError("Profil zmienił się; odśwież ustawienia.")
        if active.get("draft") and not allow_draft:
            raise ValueError("Ukończ kalibrację szkicu przed użyciem do frezowania.")
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
