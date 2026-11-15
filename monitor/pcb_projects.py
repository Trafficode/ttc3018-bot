# ---------------------------------------------------------------------------
# pcb_projects.py
# 2026-11-13
# - Independent stage attempts linked by one source, stock and X/Y setup.
# ---------------------------------------------------------------------------
"""Project preparation never connects USB, probes or starts machining."""

import copy
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import secrets
import threading
import tempfile
import time

from monitor.cam import implementation_hashes, write_json
from monitor.compensation import live_offset
from monitor.library import HASH
from monitor.pcb_flow import number
from monitor.isolation import validate_isolation_passes
from monitor.pcb_progress import require_pad_trim_acceptance
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
        self.preview_lock = threading.Lock()
        self.previews = {}

    def preview(self, package_id):
        """Source layout has no tool, thickness, CAM-job or CNC dependency."""
        from monitor.cam_geometry import mechanical_preview
        with self.preview_lock:
            if package_id in self.previews:
                return copy.deepcopy(self.previews[package_id])
            package = self.library.get(package_id)
            cad = [file for file in package["files"] if file["kind"] == "cad"]
            if len(cad) != 1:
                raise ValueError("Projekt musi zawierać jedną paczkę PCB.")
            _, data = self.library.file(package_id, cad[0]["name"])
            summary = bundle_summary(data, package["project"])
            with tempfile.TemporaryDirectory() as directory:
                report, geometry = mechanical_preview(data, package["project"], 3, Path(directory))
            matrix = report["transform"]["matrix"]
            geometry["holes"] = [{"point": [matrix[0]*h["x"]+matrix[4], matrix[3]*h["y"]+matrix[5]], "diameterMm": h["diameterMm"]} for h in summary.get("holes", [])]
            if len(self.previews) >= 20:
                self.previews.clear()
            self.previews[package_id] = geometry
            return copy.deepcopy(geometry)

    def execute(self, payload, measure_only=False):
        """Capture one explicit approval; CAM wait never grants fresh approval."""
        with self.lock, self.cam.lock, self.cnc.lock:
            run = self.read(payload.get("setupId"))
            stage = payload.get("stage")
            if stage not in KINDS or payload.get("confirmed") is not True or payload.get("fixed_probe") is not True:
                raise ValueError("Potwierdź etap, narzędzie i stałe podłączenie sondy.")
            status = self.cnc.status()
            if not status.get("connected") or not status.get("fresh") or status.get("state") != "Idle" or status.get("job", {}).get("state") in ACTIVE or status.get("z_probe", {}).get("active") or status.get("calibration", {}).get("job", {}).get("state") in ACTIVE:
                raise ValueError("Wykonanie etapu wymaga bezczynnej frezarki.")
            datum = status.get("project_datum") or {}
            if datum.get("setupId") != run["id"]:
                raise ValueError("Ustaw zero X/Y projektu.")
            position = payload.get("position")
            if not isinstance(position, list) or len(position) != 3 or not status.get("position") or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v-p) > .002 for v, p in zip(position, status["position"])):
                raise ValueError("Pozycja zmieniła się. Potwierdź etap ponownie.")
            if not status.get("probe_tested") or status.get("probe_triggered") is not False:
                raise ValueError("Sprawdź styk sondy i rozewrzyj go przed startem.")
            if not measure_only:
                number(payload, "thicknessMm", .3, 3)
                if stage == "isolation":
                    validate_isolation_passes(payload.get("isolationPasses", 1))
            result = self.cnc.project_cycle.reserve(run["id"], stage, datum["id"], position, measure_only)
            request = {**copy.deepcopy(payload), "packageId": run["packageId"]}
            thread = threading.Thread(target=self._execute, args=(request, result["cycle"]["id"]), daemon=True)
            thread.start()
            return result

    def _execute(self, payload, cycle_id):
        """Acquire store→CAM→CNC locks; the serial worker never acquires stores."""
        deadline = time.monotonic()+200
        cycle = self.cnc.project_cycle
        attempted = False
        try:
            while time.monotonic() < deadline:
                with self.lock, self.cam.lock, self.cnc.lock:
                    if not cycle.active() or cycle.record["id"] != cycle_id:
                        return
                    cycle.check_owner()
                    status = self.cnc.status()
                    datum = status.get("project_datum") or {}
                    if datum.get("id") != cycle.record["datumId"] or not status.get("fresh") or status.get("state") != "Idle" or not status.get("position") or any(abs(a-b) > .002 for a, b in zip(status["position"], cycle.record["position"])):
                        raise ValueError("Pozycja, połączenie lub zero X/Y zmieniły się przed wykonaniem.")
                    run = self.read(payload["setupId"])
                    stage = payload["stage"]
                    if cycle.record["measureOnly"]:
                        package = self.library.get(run["packageId"])
                        cad = next(file for file in package["files"] if file["kind"] == "cad")
                        _, data = self.library.file(package["id"], cad["name"])
                        box = bundle_summary(data, package["project"]).get("boundsMm")
                        if not box:
                            raise ValueError("Brak obszaru pomiaru PCB.")
                        margin = 0
                        if stage == "outline":
                            selected = self.profiles.get(payload.get("profileId"))
                            if selected["fingerprint"] != payload.get("fingerprint"):
                                raise ValueError("Profil narzędzia zmienił się. Sprawdź obszar pomiaru.")
                            margin = selected["values"]["millDiameterMm"]/2
                        bounds = {"X": [-margin, box[2]-box[0]+margin], "Y": [-margin, box[3]-box[1]+margin]}
                        cycle.record["phase"] = "loading"
                        cycle.begin_probe(self.cnc, payload, bounds)
                        return
                    current = self.state(run).get("stageStates", {}).get(stage, {})
                    passes_changed = stage == "isolation" and current.get(
                        "isolationPasses", 1) != payload.get("isolationPasses", 1)
                    if current.get("done") and not passes_changed:
                        raise ValueError("Etap jest już wykonany. Wybierz następny etap.")
                    if not current or passes_changed or current.get("stale") or current.get("state") in ("failed", "blocked", "interrupted") or current.get("profile", {}).get("fingerprint") != payload.get("fingerprint"):
                        if attempted:
                            findings = current.get("report", {}).get("checks", {}).get("findings", [])
                            raise ValueError(current.get("error") or (findings[0]["message"] if findings else "Etap nie przeszedł sprawdzenia geometrii."))
                        if not self.cam.current:
                            self.prepare(payload, cycle=True)
                            attempted = True
                    elif current.get("state") == "ready" and not self.cam.current:
                        try:
                            require_pad_trim_acceptance(self.cam.get(current["camId"]), payload)
                        except ValueError as error:
                            cycle.fail(error, "review")
                            return
                        cycle.record["phase"] = "loading"
                        self.load({**payload, "confirmedTool": True}, cycle=True)
                        cycle.begin_probe(self.cnc, payload)
                        return
                    elif current.get("state") not in ("running", "ready"):
                        raise ValueError(current.get("error") or "Nie udało się przygotować etapu.")
                time.sleep(.2)
            raise ValueError("Przekroczono czas przygotowania etapu.")
        except Exception as error:
            with self.cnc.lock:
                if cycle.record and cycle.record["id"] == cycle_id and cycle.active():
                    cycle.fail(error)
                    if isinstance(error, RuntimeError):
                        self.cnc._close(str(error))

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
        datum = status.get("project_datum") or {}
        result["xyReady"] = bool(status.get("connected") and status.get("fresh")
                                 and datum.get("setupId") == run["id"])
        stages = {}
        for kind, identity in run["stages"].items():
            try:
                item = self.cam.get(identity)
                stage = {"camId": identity, "state": item["state"],
                         "error": item.get("error"),
                         "report": item.get("report", {})}
                if kind == "isolation":
                    stage["isolationPasses"] = item.get("isolationPasses", 1)
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
                    stage["loaded"] = stage["loaded"] and result["xyReady"] and (
                        (status.get("job", {}).get("pcb_flow") or {}).get("datumId") == datum.get("id"))
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

    def create_setup(self, payload):
        """Material metadata exists before thickness, CAM or any CNC action."""
        with self.lock:
            package = self.library.get(payload.get("packageId"))
            if len([file for file in package["files"] if file["kind"] == "cad"]) != 1:
                raise ValueError("Projekt musi zawierać jedną paczkę PCB.")
            if len(list(self.root.glob("*.json"))) >= 200:
                raise ValueError("Historia przygotowania PCB jest pełna.")
            run = {"id": secrets.token_hex(32), "packageId": package["id"],
                   "thicknessMm": None, "xyOffset": None,
                   "createdAt": datetime.now(timezone.utc).isoformat(), "stages": {}}
            write_json(self.filename(run["id"]), run)
            return self.state(run)

    def prepare(self, payload, *, cycle=False):
        """Compute stages without disconnecting an idle controller."""
        with self.lock, self.cam.lock, self.cnc.lock:
            status = self.cnc.status()
            if getattr(self.cnc, "project_cycle", None) and self.cnc.project_cycle.active() and not cycle:
                raise ValueError("Poczekaj na zakończenie aktywnego etapu.")
            if (status.get("connected") and (not status.get("fresh") or status.get("state") != "Idle")) or status.get("job", {}).get(
                "state") in ACTIVE or status.get("z_probe", {}).get("active") or status.get("calibration", {}).get("job", {}).get("state") in ACTIVE:
                raise ValueError("Przygotowanie projektu wymaga bezczynnej frezarki.")
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
                    "thicknessMm"] not in (None, thickness):
                    raise ValueError("Ustawienie dotyczy innego projektu/PCB.")
                run["thicknessMm"] = thickness
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
            if kind == "isolation":
                request["allowPadTrim"] = True
                request["isolationPasses"] = validate_isolation_passes(
                    payload.get("isolationPasses", 1))
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

    def set_xy(self, payload):
        """Only an explicit operator confirmation may bind or change XY."""
        with self.lock, self.cam.lock, self.cnc.lock:
            run = self.read(payload.get("setupId"))
            if payload.get("confirmed") is not True or payload.get("mode") not in ("set", "retain"):
                raise ValueError("Potwierdź ustawienie X/Y i mocowanie materiału.")
            status = self.cnc.status()
            if not status.get("connected") or not status.get("fresh") or status.get("state") != "Idle" or (
                status.get("job", {}).get("state") in ACTIVE or status.get("z_probe", {}).get("active")
                or status.get("calibration", {}).get("job", {}).get("state") in ACTIVE
            ):
                raise ValueError("Ustawienie X/Y wymaga bezczynnej frezarki.")
            self.cnc._status()
            status = self.cnc.status()
            if not status.get("fresh") or status.get("state") != "Idle":
                raise ValueError("Ustawienie X/Y wymaga aktualnego stanu Idle.")
            expected, current = payload.get("position"), status.get("position")
            if not isinstance(expected, list) or len(expected) != 3 or not current or any(
                isinstance(a, bool) or not isinstance(a, (int, float)) or not math.isfinite(a)
                or abs(a-b) > .002 for a, b in zip(expected, current)
            ):
                raise ValueError("Pozycja zmieniła się. Sprawdź punkt odniesienia ponownie.")
            modal = self.cnc._line("$G")
            tokens = next((line[4:-1].split() for line in modal if line.startswith("[GC:") and line.endswith("]")), [])
            if "G54" not in tokens or "M5" not in tokens:
                raise ValueError("Ustawienie X/Y wymaga G54 i wyłączonego wrzeciona.")
            self._state(run)
            # Clear previous evidence before touching the controller; failures
            # must never leave an earlier confirmation usable.
            self.cnc.project_datum = None
            self.cnc.surface.invalidate("Potwierdzono nowe ustawienie X/Y.")
            self.cnc.probe.completed_job_id = None
            if payload["mode"] == "set":
                self.cnc.action("zero_xy", {})
            offset = live_offset(self.cnc._line("$#"))[:2]
            run["xyOffset"] = offset
            write_json(self.filename(run["id"]), run)
            self.cnc.project_datum = {"id": secrets.token_hex(16), "setupId": run["id"], "offset": offset}
            return self.state(run)

    def load(self, payload, *, cycle=False):
        """Explicit tool preparation binds all stage jobs to the same X/Y."""
        with self.lock, self.cam.lock, self.cnc.lock:
            if getattr(self.cnc, "project_cycle", None) and self.cnc.project_cycle.active() and not cycle:
                raise ValueError("Etap PCB jest aktywny.")
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
            if kind == "isolation" and payload.get("isolationPasses",
                item.get("isolationPasses", 1)) != item.get("isolationPasses", 1):
                raise ValueError("Szerokość izolacji zmieniła się. Przygotuj CAM ponownie.")
            require_pad_trim_acceptance(item, payload)
            # Capture completion of the previous tool before replacing its
            # sender job, even if the operator switches faster than polling.
            self._state(run)
            if item.get("workflow", {}).get("retention") == "through" and (
                payload.get("confirmedThroughCut") is not True
            ):
                raise ValueError("Potwierdź mocowanie PCB przy cięciu "
                                 "na wylot.")
            self.profiles.assert_snapshot(item["processProfile"])
            datum = status.get("project_datum") or {}
            if datum.get("setupId") != run["id"]:
                raise ValueError("Ustaw zero X/Y w przygotowaniu projektu.")
            offset = live_offset(self.cnc._line("$#"))[:2]
            expected = datum["offset"]
            if expected is not None and any(abs(a-b) > .002 for a, b in zip(
                offset, expected
            )):
                raise ValueError("Zero X/Y projektu zmieniło się. "
                                 "Potwierdź ustawienie PCB ponownie.")
            progress = self.progress.read(item["id"], status)
            loaded = progress.get("loaded") or {}
            if loaded.get("jobId") == status.get("job", {}).get("id") and (
                loaded.get("index") == len(progress["completed"]) and
                (status.get("job", {}).get("pcb_flow") or {}).get("datumId") == datum["id"] and
                not progress.get("requiresReload") and
                status.get("job", {}).get("state") not in (
                    "failed", "stopped", "completed")
            ):
                return self.state(run)
            if kind == "isolation":
                self.cnc.action("profile_select", {
                    "profile_id": item["profile"]["id"]})
            self.progress.load(item["id"], {"index": len(progress["completed"]),
                "confirmedTool": True, "confirmedReference": True,
                "acceptedPadTrim": payload.get("acceptedPadTrim")}, self.cnc,
                xy_offset=offset)
            self.cnc.jobs.program["pcb_flow"].update(
                projectSetupId=run["id"], packageId=run["packageId"], datumId=datum["id"])
            run["xyOffset"] = offset
            write_json(self.filename(run["id"]), run)
            return self.state(run)

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
