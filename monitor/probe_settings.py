"""Persistent workstation limits for Z probing, independent of the controller."""

import hashlib
import json
import os
import tempfile
from pathlib import Path


DEFAULTS = {"max_descent_mm": 10.0, "xy_feed_mm_min": 100,
            "travel_clearance_mm": 3.0, "z_feed_mm_min": 20}
ADDED_FIELDS = ("travel_clearance_mm", "z_feed_mm_min")


def bounded_settings(data):
    distance, feed = data.get("max_descent_mm"), data.get("xy_feed_mm_min")
    if type(distance) not in (float, int) or not .1 <= distance <= 10:
        raise ValueError("Maksymalny zjazd Z: zakres 0,1–10 mm.")
    if type(feed) is not int or not 25 <= feed <= 300:
        raise ValueError("Posuw XY sondy: 25–300 mm/min.")
    clearance = data.get("travel_clearance_mm")
    if type(clearance) not in (float, int) or not 1 <= clearance <= 10:
        raise ValueError("Wysokość przejazdu: zakres 1–10 mm.")
    z_feed = data.get("z_feed_mm_min")
    if type(z_feed) is not int or not 10 <= z_feed <= 60:
        raise ValueError("Posuw sondowania Z: 10–60 mm/min.")
    return {"max_descent_mm": float(distance), "xy_feed_mm_min": feed,
            "travel_clearance_mm": round(float(clearance), 4), "z_feed_mm_min": z_feed}


class ProbeSettings:
    def __init__(self, path):
        self.path = path
        self.values = DEFAULTS.copy()
        self.error = None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1:
                raise ValueError("Nieobsługiwany format ustawień.")
            self.values = bounded_settings({
                **{key: DEFAULTS[key] for key in ADDED_FIELDS}, **data,
            })
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as error:
            self.error = "Nie można odczytać ustawień sondowania: " + str(error)

    def status(self):
        revision = hashlib.sha256(json.dumps(
            [self.values, self.error], sort_keys=True).encode()).hexdigest()
        return {**self.values, "revision": revision, "error": self.error}

    def snapshot(self, request):
        current = self.status()
        if current["error"]:
            raise ValueError("Zapisz poprawne ustawienia stanowiska przed uruchomieniem.")
        if request.get("probe_settings_revision", current["revision"]) != current["revision"]:
            raise ValueError("Ustawienia stanowiska zmieniły się. Sprawdź je i potwierdź ponownie.")
        return current

    def save(self, request):
        if request.get("revision") != self.status()["revision"]:
            raise ValueError("Ustawienia sondowania zmieniły się w innym oknie.")
        settings = bounded_settings({
            **{key: self.values[key] for key in ADDED_FIELDS}, **request,
        })
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             delete=False) as output:
                temporary = Path(output.name)
                json.dump({"version": 1, **settings}, output, allow_nan=False)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        except OSError as error:
            raise RuntimeError("Nie udało się zapisać ustawień sondowania.") from error
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        self.values, self.error = settings, None
        return self.status()
