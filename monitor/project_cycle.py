"""An ephemeral operator lease authorizes one PCB tool's probe/cut cycle."""
import copy
import secrets
import time


class ProjectCycle:
    def __init__(self):
        self.record = None
        self.lease = None
        self.heartbeat_at = 0
        self.probe = None

    def active(self):
        return bool(self.record and self.record["active"])

    def status(self):
        return copy.deepcopy(self.record)

    def reserve(self, setup_id, stage, datum_id, position, measure_only=False):
        if self.active():
            raise ValueError("Etap PCB jest już aktywny.")
        self.record = {"id": secrets.token_hex(16), "setupId": setup_id,
            "stage": stage, "datumId": datum_id, "position": list(position),
            "phase": "preparing", "active": True, "error": None,
            "measureOnly": measure_only}
        self.probe = None
        self.lease = secrets.token_urlsafe(24)
        self.heartbeat_at = time.monotonic()
        return {"project_cycle_lease": self.lease, "cycle": self.status()}

    def heartbeat(self, lease, cnc):
        if not self.active() or not isinstance(lease, str) or not self.lease or not secrets.compare_digest(lease, self.lease):
            raise ValueError("Nieprawidłowa sesja wykonania etapu PCB.")
        self.heartbeat_at = time.monotonic()
        if self.probe and self.probe.active():
            self.probe.heartbeat(self.probe.lease)
        elif cnc.jobs.active() and self.record["phase"] == "cutting":
            cnc.jobs.heartbeat(cnc.jobs.lease)

    def fail(self, error, phase="failed"):
        if self.record:
            self.record.update(active=False, phase=phase, error=str(error))
        self.lease = None

    def stop(self, cnc):
        if not self.active():
            return
        phase = self.record["phase"]
        self.fail("Etap przerwany przez operatora.", "stopped")
        if self.probe and self.probe.active():
            self.probe.cancel()
        elif phase == "cutting" and cnc.jobs.active():
            cnc.jobs.control("stop", cnc.jobs.job_id)

    def check_owner(self):
        if not self.active() or time.monotonic()-self.heartbeat_at > 8:
            raise ValueError("Utrata kontaktu z przeglądarką. Wykonaj etap ponownie.")

    def begin_probe(self, cnc, payload, bounds=None):
        self.check_owner()
        cnc.calibration.invalidate_repeat("Rozpoczęto pomiar Z projektu.")
        stage = self.record["stage"]
        current = cnc.status()
        revision = {key: payload[key] for key in ("probe_settings_revision",) if key in payload}
        if stage == "drilling":
            options = {**revision, "confirmed": True, "position": current["position"],
                       "distance": payload.get("distance", 10)}
            if self.record["measureOnly"]:
                cnc.probe.start(cnc, options, recoverable_miss=True)
                cnc.surface.invalidate("Wykonano osobny pomiar Z.")
                cnc.last_probe = cnc.probe
            else:
                cnc.action("probe_start", options, project_cycle=True)
            self.probe = cnc.probe
        else:
            columns = payload.get("columns", 5) if stage == "isolation" else 3
            rows = payload.get("rows", 5) if stage == "isolation" else 3
            if not all(type(n) is int and 3 <= n <= 11 for n in (columns, rows)):
                raise ValueError("Mapa PCB wymaga 3–11 punktów na każdej osi.")
            bounds = bounds or cnc.jobs.program["bounds_mm"]
            options = {**revision, "confirmed": True, "position": current["position"],
                "job_id": cnc.jobs.job_id, "columns": columns, "rows": rows,
                "area": {"X": bounds["X"][:], "Y": bounds["Y"][:]},
                "below": .4, "distance": payload.get("distance", 10),
                "perimeterOnly": stage == "outline"}
            if self.record["measureOnly"]:
                cnc.surface.start(cnc, options, standalone_bounds=bounds,
                                  standalone_outline=stage == "outline", recoverable_miss=True)
                cnc.last_probe = cnc.surface
            else:
                cnc.action("surface_start", options, project_cycle=True)
            self.probe = cnc.surface
        self.record.update(phase="probing", jobId=cnc.jobs.job_id)

    def tick(self, cnc):
        if not self.active():
            return
        phase = self.record["phase"]
        if phase == "preparing":
            try:
                self.check_owner()
            except ValueError as error:
                self.fail(error)
            return
        if phase == "probing" and self.probe and not self.probe.active():
            try:
                self.check_owner()
                if self.probe.state != "completed":
                    raise ValueError(self.probe.error or "Pomiar Z nie został ukończony.")
                if self.record["measureOnly"]:
                    if self.record["stage"] == "drilling":
                        cnc.probe.completed_job_id = None
                    self.fail("", "measured")
                    return
                if cnc.jobs.job_id != self.record["jobId"]:
                    raise ValueError("Program zmienił się po rozpoczęciu etapu.")
                options = {"confirmed": True, "job_id": cnc.jobs.job_id}
                if self.record["stage"] != "drilling":
                    if not cnc.surface.valid:
                        raise ValueError("Mapa Z jest nieaktualna.")
                    options["surface_map_id"] = cnc.surface.map_id
                cnc.action("job_start", options, project_cycle=True)
                self.record["phase"] = "cutting"
            except Exception as error:
                self.fail(error)
                if isinstance(error, RuntimeError):
                    cnc._close(str(error))
        elif phase == "cutting" and not cnc.jobs.active():
            self.fail(cnc.jobs.error or "", cnc.jobs.state)
