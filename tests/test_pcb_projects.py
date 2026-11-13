# ---------------------------------------------------------------------------
# test_pcb_projects.py
# 2026-11-13
# - Independent stages, shared X/Y, tool changes, restart and operator API.
# ---------------------------------------------------------------------------
"""Fake sender and fake CAM artifacts, real profile/source/progress stores."""

import copy
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from monitor.cam import implementation_hashes
from monitor.library import PackageLibrary
from monitor.pcb_progress import PcbProgress
from monitor.pcb_projects import PcbProjects
from monitor.process_profiles import ProcessProfiles
from monitor.server import Handler
from project_fixture import project_archive
from test_cam import package, profile
from test_simple_drilling import simple_values
from test_simple_outline import values as outline_values


class FakeSender:
    """No serial API exists on this fake; only tool selection and loading."""

    def __init__(self):
        self.lock = threading.RLock()
        self.connected = False
        self.offset = [0, 0, 0]
        self.actions = []
        self.loads = 0
        self.jobs = SimpleNamespace(job_id=None, program={})
        self.job_state = "empty"
        self.probe = SimpleNamespace(completed_job_id=None)
        self.surface = SimpleNamespace(valid=False, job_id=None)
        self.active_profile = {"id": "default"}
        self.calibration = SimpleNamespace(profiles=SimpleNamespace(
            status=lambda: {"profiles": [profile()]},
            active=self.active_profile))

    def status(self):
        return {"connected": self.connected, "fresh": self.connected,
                "state": "Idle", "z_probe": {"active": False},
                "job": {"id": self.jobs.job_id, "state": self.job_state,
                        "pcb_flow": self.jobs.program.get("pcb_flow")}}

    def _line(self, command):
        assert command == "$#", command
        x, y, z = self.offset
        return [f"[G54:{x},{y},{z}]", "[G92:0,0,0]", "[TLO:0]"]

    def action(self, action, payload):
        assert action == "profile_select", action
        self.actions.append(action)
        self.calibration.profiles.active = {"id": payload["profile_id"]}

    def load_flow_program(self, program, operation):
        self.loads += 1
        self.jobs.job_id = f"fixture-job-{self.loads}"
        self.jobs.program = {"pcb_flow": operation}
        self.job_state = "ready"
        self.probe.completed_job_id = None
        self.surface.valid = False


class FakeCam:
    """Finalized fixtures let tests exercise progress deterministically."""

    def __init__(self, root):
        self.root = root
        self.lock = threading.RLock()
        self.items = {}

    def start(self, payload, selected, snapshot):
        kind = payload["workflow"]["operations"][0]
        identity = f"{len(self.items)+1:064x}"
        sequence = [{"file": "fixture.nc", "kind": kind,
                     "title": kind, "zPreparation": "point" if kind == (
                         "drilling") else "grid3"}]
        if kind == "drilling":
            sequence.append({**sequence[0], "file": "drill-01.nc"})
        item = {"id": identity, "state": "ready", "profile": selected,
                "processProfile": snapshot, "workflow": payload["workflow"],
                "implementationHashes": implementation_hashes(),
                "report": {"sequence": sequence}}
        self.items[identity] = copy.deepcopy(item)
        self.directory(identity).mkdir()
        return item

    def get(self, identity):
        return copy.deepcopy(self.items[identity])

    def directory(self, identity):
        return self.root / identity

    def program(self, identity, active, filename):
        return {"name": filename, "content": "fixture; never executed"}


class PcbProjectTests(unittest.TestCase):
    """Preparation and status never invoke sender execution commands."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.library = PackageLibrary(self.root / "library")
        self.package = self.library.import_package(package(project_archive()))[
            "package"]
        self.cam = FakeCam(self.root)
        self.profiles = ProcessProfiles(self.root / "profiles.json")
        self.drill = self.profiles.save({"kind": "drilling", "name": "Drill",
            "values": simple_values(), "confirmedTools": True}, {})
        self.outline = self.profiles.save({"kind": "outline", "name": "Outline",
            "values": outline_values(), "confirmedTools": True}, {})
        self.cnc = FakeSender()
        self.progress = PcbProgress(self.cam, self.profiles)
        self.store = PcbProjects(self.root / "projects", self.library, self.cam,
                                 self.profiles, self.progress, self.cnc)

    def prepare(self, kind, run=None, selected=None):
        selected = selected or {"isolation": profile(), "drilling": self.drill,
                                "outline": self.outline}[kind]
        return self.store.prepare({"packageId": self.package["id"],
            "thicknessMm": 1.6, "stage": kind,
            "setupId": run["id"] if run else None,
            "profileId": selected["id"],
            "fingerprint": selected["fingerprint"]})

    def load(self, kind, run):
        self.cnc.connected = True
        return self.store.load({"setupId": run["id"], "stage": kind,
                                "confirmedTool": True})

    def test_outline_and_drilling_prepare_without_prior_isolation(self):
        run = self.prepare("outline")
        run = self.prepare("drilling", run)
        self.assertEqual(set(run["stages"]), {"outline", "drilling"})
        self.assertFalse(run["stageStates"]["drilling"]["loaded"])
        self.assertEqual(self.cnc.actions, [])
        with self.assertRaises(ValueError):
            self.prepare("drilling", run, {"id": "missing", "fingerprint": "x"})

    def test_shared_xy_is_bound_on_load_and_changes_block_other_stage(self):
        run = self.prepare("drilling")
        run = self.prepare("outline", run)
        run = self.load("drilling", run)
        self.assertEqual(run["xyOffset"], [0, 0])
        self.load("outline", run)
        self.assertEqual(self.cnc.loads, 2)
        self.cnc.offset = [1, 0, 0]
        with self.assertRaisesRegex(ValueError, "Zero X/Y"):
            self.load("drilling", run)
        self.assertEqual(self.cnc.loads, 2)

    def test_repeated_load_is_idempotent_and_never_probes_or_starts(self):
        run = self.load("drilling", self.prepare("drilling"))
        first = self.cnc.jobs.job_id
        self.load("drilling", run)
        self.assertEqual(self.cnc.jobs.job_id, first)
        self.assertEqual(self.cnc.loads, 1)
        self.assertTrue(all(action == "profile_select"
                            for action in self.cnc.actions))

    def test_next_diameter_requires_new_load_and_fresh_z(self):
        run = self.load("drilling", self.prepare("drilling"))
        self.cnc.probe.completed_job_id = self.cnc.jobs.job_id
        state = self.store.state(self.store.read(run["id"]))
        self.assertTrue(state["stageStates"]["drilling"]["zReady"])
        self.cnc.job_state = "completed"
        state = self.store.state(self.store.read(run["id"]))
        drilling = state["stageStates"]["drilling"]
        self.assertEqual(drilling["index"], 1)
        self.assertFalse(drilling["loaded"])
        self.assertFalse(drilling["zReady"])
        state = self.load("drilling", run)
        self.assertEqual(self.cnc.loads, 2)
        self.assertFalse(state["stageStates"]["drilling"]["zReady"])

    def test_restart_invalidates_loaded_stage_evidence(self):
        run = self.load("drilling", self.prepare("drilling"))
        self.store.progress = PcbProgress(self.cam, self.profiles)
        state = self.store.state(self.store.read(run["id"]))
        self.assertTrue(state["stageStates"]["drilling"]["requiresReload"])
        self.assertFalse(state["stageStates"]["drilling"]["loaded"])

    def test_fast_switch_captures_completion_before_replacing_sender_job(self):
        run = self.prepare("drilling")
        run = self.prepare("outline", run)
        self.load("outline", run)
        self.cnc.job_state = "completed"
        state = self.load("drilling", run)
        self.assertTrue(state["stageStates"]["outline"]["done"])
        self.assertFalse(state["stageStates"]["drilling"]["zReady"])

    def test_changed_profile_marks_result_stale(self):
        run = self.prepare("drilling")
        self.profiles.save({"kind": "drilling", "name": "Changed",
            "values": simple_values(drillFeed=20), "confirmedTools": True,
            "id": self.drill["id"],
            "expectedFingerprint": self.drill["fingerprint"]}, {})
        state = self.store.state(self.store.read(run["id"]))
        self.assertTrue(state["stageStates"]["drilling"]["stale"])
        with self.assertRaisesRegex(ValueError, "oblicz PCB ponownie"):
            self.load("drilling", run)

    def test_operator_api_rejects_ingestion_token_and_foreign_origin(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.control_token = "operator-fixture"
        server.pcb_projects = self.store
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = f"http://127.0.0.1:{server.server_port}"
        def request(payload=None, operator=False, origin=base):
            headers = {"Authorization": "Bearer ingestion-fixture",
                       "Content-Type": "application/json", "Origin": origin}
            if operator:
                headers["X-PiloMill-Token"] = server.control_token
            route = "/api/pcb-projects" if payload is None else (
                "/api/pcb-projects/prepare")
            try:
                with urlopen(Request(base + route, None if payload is None else
                    json.dumps(payload).encode(), headers)) as response:
                    return response.status
            except HTTPError as error:
                error.close()
                return error.code
        self.assertEqual(request(), 403)
        self.assertEqual(request(operator=True), 200)
        self.assertEqual(request({}, True, "http://foreign"), 400)
        self.assertEqual(request({}, True), 400)
        self.assertEqual(self.cnc.actions, [])


if __name__ == "__main__":
    unittest.main()

# ---------------------------------------------------------------------------
# end of file
# ---------------------------------------------------------------------------
