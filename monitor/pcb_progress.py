# ---------------------------------------------------------------------------
# pcb_progress.py
# 2026-11-09
# - Persist operator workflow progress from actual sender completion evidence.
# ---------------------------------------------------------------------------
"""Preparing/loading never starts motion; no checkbox can complete a phase."""

import secrets
from datetime import datetime, timezone

from monitor.cam import write_json


class PcbProgress:
    """Progress shares the CAM lock and tracks one exact loaded sender job."""

    def __init__(self, collection, process_profiles=None):
        self.collection = collection
        self.process_profiles = process_profiles
        self.session = secrets.token_hex(16)

    def read(self, item_id, status):
        """Accept completion only from the exact job in this server session."""
        import json
        directory = self.collection.directory(item_id)
        filename = directory / "progress.json"
        try:
            progress = json.loads(filename.read_text())
        except FileNotFoundError:
            progress = {"completed": [], "loaded": None}
        loaded = progress.get("loaded")
        job = status.get("job", {})
        if loaded and loaded["session"] == self.session and (
            loaded["jobId"] == job.get("id")
            and loaded["index"] == len(progress["completed"])
            and job.get("state") == "completed"
        ):
            progress["completed"].append(loaded["index"])
            progress.setdefault("events", []).append({
                "index": loaded["index"], "jobId": loaded["jobId"],
                "completedAt": datetime.now(timezone.utc).isoformat(),
                "commands": job.get("total"),
                "acknowledged": job.get("acknowledged"),
                "mapId": status.get("surface_map", {}).get("id")})
            progress["xyOffset"] = job.get("pcb_flow", {}).get("xyOffset")
            samples = status.get("surface_map", {}).get("samples", [])
            if samples:
                heights = [sample["z"] for sample in samples]
                progress["surfaceSpreadMm"] = max(heights) - min(heights)
            progress["loaded"] = None
            write_json(filename, progress)
        progress["requiresReload"] = bool(progress.get("loaded") and (
            progress["loaded"]["session"] != self.session
            or progress["loaded"]["jobId"] != job.get("id")))
        return progress

    def load(self, item_id, payload, cnc):
        """Explicitly load only the next operation after tool/setup review."""
        with self.collection.lock, cnc.lock:
            item = self.collection.get(item_id)
            if item.get("processProfile") and self.process_profiles:
                self.process_profiles.assert_snapshot(item["processProfile"])
            sequence = item.get("report", {}).get("sequence", [])
            progress = self.read(item_id, cnc.status())
            index = len(progress["completed"])
            if payload.get("index") != index or index >= len(sequence):
                raise ValueError("Nie można pominąć etapu zlecenia.")
            if payload.get("confirmedTool") is not True or payload.get(
                "confirmedReference") is not True:
                raise ValueError("Potwierdź narzędzie i miejsce pomiaru Z.")
            operation = sequence[index]
            active = cnc.calibration.profiles.active
            program = self.collection.program(item_id, active,
                                              operation["file"])
            if operation["kind"] != "isolation":
                # Flat tools use explicit mechanical CAM parameters, not the
                # V-bit width/depth calibration model. No axis setting changes.
                cnc.action("profile_select", {"profile_id": "default"})
            cnc.load_flow_program(program, {"id": item_id, "index": index,
                                           "processProfile": item.get(
                                               "processProfile"),
                                           "xyOffset": progress.get("xyOffset"),
                                           "surfaceSpreadMm": progress.get(
                                               "surfaceSpreadMm", 0),
                                           **operation})
            progress["loaded"] = {"index": index, "session": self.session,
                                  "jobId": cnc.jobs.job_id}
            progress.pop("requiresReload", None)
            write_json(self.collection.directory(item_id) / "progress.json",
                       progress)
            return progress

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
