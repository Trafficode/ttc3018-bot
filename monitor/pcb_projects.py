# ---------------------------------------------------------------------------
# pcb_projects.py
# 2026-11-13
# - Independent stage attempts linked by one source, stock and X/Y setup.
# ---------------------------------------------------------------------------
"""Project preparation never connects USB, probes or starts machining."""

import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import threading

from monitor.cam import implementation_hashes, write_json
from monitor.compensation import live_offset
from monitor.library import HASH
from monitor.pcb_flow import number
from monitor.project_bundle import bundle_summary

KINDS = ("isolation", "drilling", "outline")
ACTIVE = ("running", "paused", "pausing", "draining", "resuming")


class PcbProjects:
    """Separate CAM attempts share a datum without a forced stage sequence."""

    def __init__(self, root, library, cam, profiles, progress, cnc):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.library, self.cam = library, cam
        self.profiles, self.progress, self.cnc = profiles, progress, cnc
        self.lock = threading.RLock()

    def filename(self, identity):
        """Never accept client paths or symlink records."""
        if not isinstance(identity, str) or not HASH.fullmatch(identity):
            raise ValueError("Niepoprawny identyfikator przygotowania PCB.")
        filename = self.root / (identity + ".json")
        if filename.is_symlink():
            raise ValueError("Niedozwolony zapis przygotowania PCB.")
        return filename

    def read(self, identity):
        """Source packages remain immutable and independently hash-checked."""
        run = json.loads(self.filename(identity).read_text("utf-8"))
        if run.get("id") != identity:
            raise ValueError("Uszkodzony zapis przygotowania PCB.")
        self.library.get(run["packageId"])
        return run

    def state(self, run):
        """Derive completion and fresh-Z state from the real sender evidence."""
        with self.cam.lock:
            return self._state(run)

    def _state(self, run):
        """Progress readback shares the lock used by the legacy flow routes."""
        result = copy.deepcopy(run)
        status = self.cnc.status()
        stages = {}
        for kind, identity in run["stages"].items():
            try:
                item = self.cam.get(identity)
                stage = {"camId": identity, "state": item["state"],
                         "error": item.get("error"),
                         "report": item.get("report", {})}
                stage["profile"] = item.get("profile") if kind == (
                    "isolation") else item.get("processProfile", {}).get(
                        "profiles", {}).get(kind)
                stale = item.get("implementationHashes") != (
                    implementation_hashes())
                if item.get("processProfile"):
                    self.profiles.assert_snapshot(item["processProfile"])
                if kind == "isolation":
                    available = self.cnc.calibration.profiles.status()[
                        "profiles"]
                    stale = stale or not any(p["fingerprint"] == item[
                        "profile"].get("fingerprint") for p in available)
                stage["stale"] = stale
                if item["state"] == "ready":
                    progress = self.progress.read(identity, status)
                    index = len(progress["completed"])
                    sequence = item["report"].get("sequence", [])
                    stage.update(index=index, total=len(sequence),
                                 done=index == len(sequence),
                                 operation=sequence[index] if index < len(
                                     sequence) else None,
                                 requiresReload=progress.get("requiresReload"))
                    loaded = progress.get("loaded") or {}
                    stage["loaded"] = bool(loaded.get("jobId")) and (
                        loaded.get("jobId") == status.get("job", {}).get("id")
                        and loaded.get("index") == index
                        and not progress.get("requiresReload"))
                    stage["zReady"] = stage["loaded"] and status.get(
                        "connected") and status.get("fresh") and (
                        self.cnc.probe.completed_job_id == self.cnc.jobs.job_id
                        if kind == "drilling" else self.cnc.surface.valid and
                        self.cnc.surface.job_id == self.cnc.jobs.job_id)
                stages[kind] = stage
            except (OSError, ValueError, KeyError) as error:
                stages[kind] = {"camId": identity, "state": "stale",
                                "stale": True, "error": str(error)}
        result["stageStates"] = stages
        return result

    def list(self, package_id):
        """Return bounded recent setups, without restoring machine evidence."""
        with self.lock:
            result = []
            for filename in self.root.glob("*.json"):
                try:
                    run = self.read(filename.stem)
                    if run["packageId"] == package_id:
                        result.append(self.state(run))
                except (OSError, ValueError, KeyError):
                    continue
            return sorted(result, key=lambda item: item["createdAt"],
                          reverse=True)[:20]

    def prepare(self, payload):
        """Prepare one stage offline; callers may queue stages independently."""
        with self.lock, self.cam.lock, self.cnc.lock:
            status = self.cnc.status()
            if status.get("connected") or status.get("job", {}).get(
                "state") in ACTIVE or status.get("z_probe", {}).get("active"):
                raise ValueError("Rozłącz CNC przed przygotowaniem projektu.")
            kind = payload.get("stage")
            if kind not in KINDS:
                raise ValueError("Wybierz etap projektu PCB.")
            thickness = number(payload, "thicknessMm", .3, 3)
            package = self.library.get(payload.get("packageId"))
            cad = [file for file in package["files"] if file["kind"] == "cad"]
            if len(cad) != 1:
                raise ValueError("Projekt musi zawierać jedną paczkę PCB.")
            record, data = self.library.file(package["id"], cad[0]["name"])
            capability = bundle_summary(data, package["project"])["stages"][
                kind]
            if not capability["available"]:
                raise ValueError(capability.get("reason") or
                                 "Brak danych etapu.")
            if payload.get("setupId"):
                run = self.read(payload["setupId"])
                if run["packageId"] != package["id"] or run[
                    "thicknessMm"] != thickness:
                    raise ValueError("Ustawienie dotyczy innego projektu/PCB.")
            else:
                if len(list(self.root.glob("*.json"))) >= 200:
                    raise ValueError("Historia przygotowania PCB jest pełna.")
                run = {"id": secrets.token_hex(32), "packageId": package["id"],
                       "thicknessMm": thickness, "xyOffset": None,
                       "createdAt": datetime.now(timezone.utc).isoformat(),
                       "stages": {}}
            profile = next((p for p in self.cnc.calibration.profiles.status()[
                "profiles"] if p["id"] == payload.get("profileId")), {})
            request = {"packageId": package["id"], "name": record["name"],
                       "confirmedDatum": True, "profileFingerprint":
                           payload.get("fingerprint")}
            selection = {} if kind == "isolation" else {kind: {
                "id": payload.get("profileId"),
                "fingerprint": payload.get("fingerprint")}}
            snapshot, workflow, clearance = self.profiles.resolve({
                "operations": [kind], "processProfiles": selection,
                "material": {"thicknessMm": thickness,
                    "confirmedThroughCut": payload.get(
                        "confirmedThroughCut") is True},
                "clearanceMm": 3, "confirmedSetup": True}, profile)
            request.update(workflow=workflow, clearanceMm=clearance)
            item = self.cam.start(request, profile, snapshot)
            run["stages"][kind] = item["id"]
            write_json(self.filename(run["id"]), run)
            return self.state(run)

    def load(self, payload):
        """Explicit tool preparation binds all stage jobs to the same X/Y."""
        with self.lock, self.cam.lock, self.cnc.lock:
            run = self.read(payload.get("setupId"))
            kind = payload.get("stage")
            if kind not in run["stages"]:
                raise ValueError("Etap nie został przygotowany.")
            if payload.get("confirmedTool") is not True:
                raise ValueError("Potwierdź zamontowane narzędzie.")
            status = self.cnc.status()
            if not status.get("connected") or not status.get("fresh") or (
                status.get("state") != "Idle" or status.get("job", {}).get(
                    "state") in ACTIVE or status.get("z_probe", {}).get(
                        "active")
            ):
                raise ValueError("Przygotowanie narzędzia wymaga stanu Idle.")
            item = self.cam.get(run["stages"][kind])
            # Capture completion of the previous tool before replacing its
            # sender job, even if the operator switches faster than polling.
            self._state(run)
            if item.get("workflow", {}).get("retention") == "through" and (
                payload.get("confirmedThroughCut") is not True
            ):
                raise ValueError("Potwierdź mocowanie PCB przy cięciu "
                                 "na wylot.")
            self.profiles.assert_snapshot(item["processProfile"])
            if kind == "isolation":
                self.cnc.action("profile_select", {
                    "profile_id": item["profile"]["id"]})
            offset = live_offset(self.cnc._line("$#"))[:2]
            expected = run["xyOffset"]
            if expected is not None and any(abs(a-b) > .002 for a, b in zip(
                offset, expected
            )):
                raise ValueError("Zero X/Y projektu zmieniło się. "
                                 "Przygotuj nowe ustawienie PCB.")
            progress = self.progress.read(item["id"], status)
            loaded = progress.get("loaded") or {}
            if loaded.get("jobId") == status.get("job", {}).get("id") and (
                loaded.get("index") == len(progress["completed"]) and
                not progress.get("requiresReload") and
                status.get("job", {}).get("state") not in (
                    "failed", "stopped", "completed")
            ):
                return self.state(run)
            self.progress.load(item["id"], {"index": len(progress["completed"]),
                "confirmedTool": True, "confirmedReference": True}, self.cnc,
                xy_offset=offset)
            self.cnc.jobs.program["pcb_flow"].update(
                projectSetupId=run["id"], packageId=run["packageId"])
            run["xyOffset"] = offset
            write_json(self.filename(run["id"]), run)
            return self.state(run)

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
