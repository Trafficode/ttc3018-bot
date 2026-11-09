# ---------------------------------------------------------------------------
# process_profiles.py
# 2026-11-09
# - Named PCB machining/setup recipes, independent of measured V-bit models.
# ---------------------------------------------------------------------------
"""Recipes remove repeated job inputs; they never change controller settings."""

import copy
import json
from pathlib import Path
import secrets
import threading

from monitor.cam import write_json
from monitor.pcb_flow import FLOW_LIMITS, number, validate_flow
from monitor.profiles import fingerprint


class ProcessProfiles:
    """Persist validated recipes with optimistic revisions and source binding."""

    def __init__(self, filename):
        self.filename = Path(filename)
        self.lock = threading.RLock()
        self.data = {"version": 1, "active": None, "profiles": []}
        self.error = None
        try:
            data = json.loads(self.filename.read_text("utf-8"))
            if data.get("version") != 1 or not isinstance(
                data.get("profiles"), list
            ) or len(data["profiles"]) > 30:
                raise ValueError("Niepoprawny format profili obróbki PCB.")
            for profile in data["profiles"]:
                if fingerprint(profile) != profile["fingerprint"]:
                    raise ValueError("Zmienione dane profilu obróbki PCB.")
                self.validate_values(profile["values"])
            if data.get("active") not in [None] + [
                profile["id"] for profile in data["profiles"]
            ]:
                raise ValueError("Brak wybranego profilu w zapisanym zestawie.")
            self.data = data
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.error = str(error)

    @staticmethod
    def validate_values(data):
        """Validate tool/setup properties without inventing stock thickness."""
        if not isinstance(data, dict):
            raise ValueError("Brak parametrów profilu.")
        result = {key: number(data, key, low, high)
                  for key, (low, high) in FLOW_LIMITS.items()
                  if key != "thicknessMm"}
        result["clearanceMm"] = number(data, "clearanceMm", 1, 10)
        if data.get("retention") not in ("skin", "tabs"):
            raise ValueError("Wybierz sposób oddzielenia PCB.")
        result["retention"] = data["retention"]
        if result["skinMm"] <= result["uncertaintyMm"]:
            raise ValueError("Pozostawiona warstwa musi przekraczać "
                             "budżet błędu grubości i Z.")
        return result

    def status(self):
        """Read-only snapshots contain no operator token or host settings."""
        with self.lock:
            return copy.deepcopy({**self.data, "error": self.error})

    def _commit(self):
        if self.error:
            raise ValueError("Przywróć uszkodzone profile z kopii.")
        self.filename.parent.mkdir(parents=True, exist_ok=True)
        write_json(self.filename, self.data)

    def get(self, profile_id):
        """Resolve only a known recipe, never a browser filesystem path."""
        if self.error:
            raise ValueError(self.error)
        profile = next((value for value in self.data["profiles"]
                        if value["id"] == profile_id), None)
        if profile is None:
            raise ValueError("Wybierz zapisany profil obróbki PCB.")
        return copy.deepcopy(profile)

    def save(self, payload, isolation):
        """Bind an explicitly reviewed recipe to the selected V calibration."""
        with self.lock:
            name = payload.get("name")
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60:
                raise ValueError("Nazwa profilu: 1–60 znaków.")
            if any(ord(char) < 32 for char in name):
                raise ValueError("Niepoprawna nazwa profilu.")
            if payload.get("confirmedTools") is not True:
                raise ValueError("Potwierdź parametry narzędzi i mocowania.")
            if not isolation.get("model"):
                raise ValueError("Najpierw wybierz skalibrowany "
                                 "profil frezu V.")
            previous = self.get(payload["id"]) if payload.get("id") else None
            if previous and previous["fingerprint"] != payload.get(
                "expectedFingerprint"
            ):
                raise ValueError("Profil zmienił się; odśwież dane.")
            if not previous and len(self.data["profiles"]) >= 30:
                raise ValueError("Limit 30 profili obróbki PCB.")
            profile_id = previous["id"] if previous else secrets.token_hex(8)
            profile = {"id": profile_id,
                       "name": name.strip(),
                       "revision": previous["revision"] + 1 if previous else 1,
                       "isolation": {key: isolation[key] for key in
                                     ("id", "name", "fingerprint")},
                       "values": self.validate_values(payload.get("values"))}
            profile["fingerprint"] = fingerprint(profile)
            replacement = [value for value in self.data["profiles"]
                           if value["id"] != profile["id"]] + [profile]
            old = copy.deepcopy(self.data)
            self.data.update(profiles=replacement, active=profile["id"])
            try:
                self._commit()
            except Exception:
                self.data = old
                raise
            return copy.deepcopy(profile)

    def select(self, payload):
        """Selection affects the next plan, never a running program."""
        with self.lock:
            profile = self.get(payload.get("id"))
            if profile["fingerprint"] != payload.get("fingerprint"):
                raise ValueError("Profil zmienił się; odśwież dane.")
            old = self.data["active"]
            self.data["active"] = profile["id"]
            try:
                self._commit()
            except Exception:
                self.data["active"] = old
                raise
            return profile

    def assert_snapshot(self, snapshot):
        """Changed recipes require recalculation, not silent NC adaptation."""
        profile = self.get(snapshot["id"])
        if profile["fingerprint"] != snapshot["fingerprint"]:
            raise ValueError("Profil obróbki zmienił się; oblicz PCB ponownie.")

    def resolve(self, payload, isolation):
        """Merge only stock-specific overrides into an immutable job snapshot."""
        with self.lock:
            profile = self.get(payload.get("processProfileId"))
            if profile["fingerprint"] != payload.get("processFingerprint"):
                raise ValueError("Profil obróbki zmienił się; odśwież wybór.")
            if profile["isolation"]["fingerprint"] != isolation.get(
                "fingerprint"
            ) or profile["isolation"]["id"] != isolation.get("id"):
                raise ValueError("Wybierz profil frezu V zapisany w zestawie: "
                                 + profile["isolation"]["name"])
            material = payload.get("material")
            if not isinstance(material, dict):
                raise ValueError("Wprowadź zmierzoną grubość laminatu.")
            values = {**profile["values"],
                      "thicknessMm": material.get("thicknessMm"),
                      "confirmedSetup": payload.get("confirmedSetup") is True}
            for key in ("skinMm", "retention"):
                if key in material:
                    values[key] = material[key]
            flow = validate_flow(values)
            return profile, flow, profile["values"]["clearanceMm"]

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
