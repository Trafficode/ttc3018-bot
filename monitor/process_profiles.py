# ---------------------------------------------------------------------------
# process_profiles.py
# 2026-11-13
# - Separate drilling and outline profiles with compatible legacy recipes.
# ---------------------------------------------------------------------------
"""Recipes remove repeated job inputs; they never change controller settings."""

import copy
import json
from pathlib import Path
import secrets
import threading

from monitor.cam import write_json
from monitor.pcb_flow import (
    FLOW_LIMITS, number, selected_operations, validate_flow,
    validate_tool_values,
)
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
                self.validate_values(profile["values"],
                                     profile.get("kind", "legacy"))
            if data.get("active") not in [None] + [
                profile["id"] for profile in data["profiles"]
            ]:
                raise ValueError("Brak wybranego profilu w zapisanym zestawie.")
            active = data.get("activeByKind", {})
            if not isinstance(active, dict):
                raise ValueError("Niepoprawne wybory profili narzędzi.")
            for kind, identity in active.items():
                matching = [profile for profile in data["profiles"]
                            if profile["id"] == identity and profile.get(
                                "kind", "legacy") in (kind, "legacy")]
                if kind not in ("drilling", "outline") or not matching:
                    raise ValueError("Brak wybranego profilu narzędzia.")
            self.data = data
        except FileNotFoundError:
            pass
        except (OSError, ValueError, KeyError, TypeError) as error:
            self.error = str(error)

    @staticmethod
    def validate_values(data, kind="legacy"):
        """Validate tool/setup properties without inventing stock thickness."""
        if not isinstance(data, dict):
            raise ValueError("Brak parametrów profilu.")
        if kind in ("drilling", "outline"):
            return validate_tool_values(data, kind)
        if kind != "legacy":
            raise ValueError("Niepoprawny rodzaj profilu.")
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
        """Save reviewed tool values; only legacy recipes bind V calibration."""
        with self.lock:
            name = payload.get("name")
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60:
                raise ValueError("Nazwa profilu: 1–60 znaków.")
            if any(ord(char) < 32 for char in name):
                raise ValueError("Niepoprawna nazwa profilu.")
            if payload.get("confirmedTools") is not True:
                raise ValueError("Potwierdź parametry narzędzi i mocowania.")
            kind = payload.get("kind", "legacy")
            if kind == "legacy" and not isolation.get("model"):
                raise ValueError("Najpierw wybierz skalibrowany "
                                 "profil frezu V.")
            previous = self.get(payload["id"]) if payload.get("id") else None
            if previous and previous.get("kind", "legacy") != kind:
                raise ValueError("Rodzaj zapisanego profilu "
                                 "nie może się zmienić.")
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
                       "values": self.validate_values(
                           payload.get("values"), kind)}
            if kind == "legacy":
                profile["isolation"] = {key: isolation[key] for key in
                                        ("id", "name", "fingerprint")}
            else:
                profile["kind"] = kind
            profile["fingerprint"] = fingerprint(profile)
            replacement = [value for value in self.data["profiles"]
                           if value["id"] != profile["id"]] + [profile]
            old = copy.deepcopy(self.data)
            self.data.update(profiles=replacement, active=profile["id"])
            if kind != "legacy":
                active = dict(self.data.get("activeByKind", {}))
                active[kind] = profile["id"]
                self.data["activeByKind"] = active
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
            kind = payload.get("kind", profile.get("kind"))
            if kind is not None and (
                kind not in ("drilling", "outline") or
                profile.get("kind", "legacy") not in (kind, "legacy")
            ):
                raise ValueError("Wybrano profil innego rodzaju obróbki.")
            old = copy.deepcopy(self.data)
            self.data["active"] = profile["id"]
            if kind:
                active = dict(self.data.get("activeByKind", {}))
                active[kind] = profile["id"]
                self.data["activeByKind"] = active
            try:
                self._commit()
            except Exception:
                self.data = old
                raise
            return profile

    def assert_snapshot(self, snapshot):
        """Changed recipes require recalculation, not silent NC adaptation."""
        if snapshot.get("kind") == "selection":
            if fingerprint(snapshot) != snapshot.get("fingerprint"):
                raise ValueError("Zmienione dane wybranych profili.")
            for profile in snapshot["profiles"].values():
                self.assert_snapshot(profile)
            return
        profile = self.get(snapshot["id"])
        if profile["fingerprint"] != snapshot["fingerprint"]:
            raise ValueError("Profil obróbki zmienił się; oblicz PCB ponownie.")

    def resolve(self, payload, isolation):
        """Merge only stock-specific overrides into an immutable job snapshot."""
        with self.lock:
            if "processProfiles" in payload:
                return self.resolve_selection(payload, isolation)
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

    def resolve_selection(self, payload, isolation):
        """Compose only requested tools; mechanical jobs need no V model."""
        requested = selected_operations(payload)
        selections = payload.get("processProfiles")
        material = payload.get("material")
        if not isinstance(selections, dict) or not isinstance(material, dict):
            raise ValueError("Wybierz profile i zmierzoną grubość PCB.")
        profiles = {}
        operation_settings = {}
        for kind in requested:
            if kind == "isolation":
                continue
            selection = selections.get(kind)
            if not isinstance(selection, dict):
                raise ValueError("Wybierz profil dla każdej operacji.")
            profile = self.get(selection.get("id"))
            if profile["fingerprint"] != selection.get("fingerprint"):
                raise ValueError("Profil zmienił się; odśwież wybór.")
            if profile.get("kind", "legacy") not in (kind, "legacy"):
                raise ValueError("Wybrano profil innego rodzaju obróbki.")
            values = dict(profile["values"])
            if kind == "drilling" and profile.get("kind") is None:
                values["drillDiameterMm"] = 0
            if kind == "outline":
                for key in ("skinMm", "retention"):
                    if key in material:
                        values[key] = material[key]
            profiles[kind] = profile
            operation_settings[kind] = validate_tool_values(values, kind)
        flow = validate_flow({
            "operations": requested, "operationSettings": operation_settings,
            "thicknessMm": material.get("thicknessMm"),
            "confirmedSetup": payload.get("confirmedSetup") is True,
            "confirmedThroughCut": material.get("confirmedThroughCut") is True,
        })
        heights = [values["clearanceMm"]
                   for values in operation_settings.values()]
        if "isolation" in requested:
            heights.append(number(payload, "clearanceMm", 1, 10))
        clearance = max(heights) if heights else number(
            payload, "clearanceMm", 1, 10)
        names = [value["name"] for value in profiles.values()]
        if "isolation" in requested:
            names.insert(0, isolation.get("name", "Ścieżki"))
        snapshot = {"kind": "selection", "name": " · ".join(names),
                    "profiles": profiles}
        snapshot["fingerprint"] = fingerprint(snapshot)
        return snapshot, flow, clearance

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
